"""Complaint document rendering delegated from ComplaintDocumentBuilder."""

from __future__ import annotations

try:
    from docx import Document as DocxDocument
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    HAS_DOCX = True
except ImportError:  # pragma: no cover - optional dependency
    DocxDocument = None
    WD_ALIGN_PARAGRAPH = None
    Inches = None
    Pt = None
    HAS_DOCX = False

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    HAS_REPORTLAB = True
except ImportError:  # pragma: no cover - optional dependency
    colors = None
    TA_CENTER = None
    letter = None
    ParagraphStyle = None
    getSampleStyleSheet = None
    inch = None
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
    Table = None
    TableStyle = None
    HAS_REPORTLAB = False

from mediator.formal_document import (
    ComplaintPhase,
    _build_anchored_chronology_summary,
    _build_factual_allegation_groups,
    _clean_sentence,
    _clean_text,
    _listify,
    _utc_now_isoformat,
    build_caption_party_block_lines,
    build_case_caption_table,
    build_case_caption_text_lines,
    build_case_detail_lines,
    make_page_footer_renderer,
)

def render_text(self, draft: Dict[str, Any]) -> str:
    caption = draft.get("caption", {}) if isinstance(draft.get("caption"), dict) else {}
    parties = draft.get("parties", {}) if isinstance(draft.get("parties"), dict) else {}
    intake_summary = [item for item in _listify(draft.get("intake_summary")) if isinstance(item, dict)]
    lines: List[str] = []

    def _append_blank() -> None:
        if lines and lines[-1] != "":
            lines.append("")

    def _format_id_list(values: Any, *, prefix: str = "") -> str:
        entries = [_clean_text(value) for value in _listify(values) if _clean_text(value)]
        return f"{prefix}{', '.join(entries)}" if entries else ""

    def _claim_rows(claim: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = [
            row
            for row in _listify(claim.get("supporting_fact_provenance"))
            if isinstance(row, dict) and _clean_text(row.get("text") or "")
        ]
        if rows:
            return rows
        return [
            row
            for row in _listify(claim.get("supporting_fact_entries"))
            if isinstance(row, dict) and _clean_text(row.get("text") or "")
        ]

    def _intake_clarifications() -> List[str]:
        focus_tokens = {
            "when",
            "date",
            "time",
            "timeline",
            "after",
            "before",
            "who",
            "actor",
            "title",
            "because",
            "caus",
            "grievance",
            "hearing",
            "appeal",
            "retaliat",
            "notice",
        }
        clarifications: List[str] = []
        seen = set()
        for item in intake_summary:
            question = _clean_text(item.get("question") or "")
            answer = _clean_text(item.get("answer") or "")
            if not answer:
                continue
            lowered = f"{question} {answer}".lower()
            if not any(token in lowered for token in focus_tokens):
                continue
            sentence = _clean_sentence(answer)
            if not sentence:
                continue
            marker = sentence.lower()
            if marker in seen:
                continue
            seen.add(marker)
            clarifications.append(sentence)
        return clarifications

    lines.append(str(draft.get("court_header") or "IN THE COURT OF COMPETENT JURISDICTION"))
    if caption.get("division_line"):
        lines.append(str(caption["division_line"]))
    if caption.get("county_line"):
        lines.append(str(caption["county_line"]))
    lines.append("")

    case_number = draft.get("case_number") or caption.get("case_number") or "________________"
    lines.extend(
        build_case_caption_text_lines(
            parties,
            {"case_number": case_number, **caption},
            assigned_judge_label="Assigned to:",
        )
    )
    lines.append("")
    lines.append("COMPLAINT")
    if caption.get("jury_demand_notice"):
        lines.append(str(caption["jury_demand_notice"]))

    _append_blank()
    lines.append("NATURE OF THE ACTION")
    lines.append(_clean_sentence(draft.get("nature_of_action")))

    _append_blank()
    lines.append("PARTIES")
    plaintiffs_list = _listify(parties.get("plaintiffs"))
    defendants_list = _listify(parties.get("defendants"))
    for index, party in enumerate(plaintiffs_list, 1):
        lines.append(f"{index}. Plaintiff {party} is an aggrieved party bringing this action.")
    start_index = len(plaintiffs_list)
    for offset, party in enumerate(defendants_list, 1):
        lines.append(f"{start_index + offset}. Defendant {party} is alleged to be responsible for the acts described below.")

    _append_blank()
    lines.append("JURISDICTION AND VENUE")
    lines.append(_clean_sentence(draft.get("jurisdiction_statement")))
    lines.append(_clean_sentence(draft.get("venue_statement")))

    _append_blank()
    lines.append("FACTUAL ALLEGATIONS")
    allegation_counter = 0
    allegation_groups = draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else []
    if allegation_groups:
        for group in allegation_groups:
            if not isinstance(group, dict):
                continue
            if group.get("title"):
                lines.append(str(group["title"]).upper())
            for entry in _listify(group.get("paragraphs")):
                if not isinstance(entry, dict):
                    continue
                text = _clean_sentence(entry.get("text"))
                if not text:
                    continue
                allegation_counter += 1
                number = entry.get("number") if entry.get("number") not in (None, "") else allegation_counter
                lines.append(f"{number}. {text}")
    else:
        allegation_entries = [
            entry
            for entry in _listify(draft.get("factual_allegation_paragraphs"))
            if isinstance(entry, dict) and _clean_text(entry.get("text") or "")
        ]
        if allegation_entries:
            for index, entry in enumerate(allegation_entries, 1):
                text = _clean_sentence(entry.get("text"))
                if not text:
                    continue
                lines.append(f"{index}. {text}")
                trace_bits = []
                fact_ids = _format_id_list(entry.get("fact_ids"), prefix="fact ids: ")
                source_ids = _format_id_list(entry.get("source_artifact_ids"), prefix="artifact ids: ")
                if fact_ids:
                    trace_bits.append(fact_ids)
                if source_ids:
                    trace_bits.append(source_ids)
                if trace_bits:
                    lines.append(f"   Support Trace: {'; '.join(trace_bits)}")
        else:
            for index, allegation in enumerate(_listify(draft.get("factual_allegations")), 1):
                lines.append(f"{index}. {_clean_sentence(allegation)}")

    incorporated_clarifications = _intake_clarifications()
    if incorporated_clarifications:
        _append_blank()
        lines.append("INTAKE CLARIFICATIONS INCORPORATED")
        for index, sentence in enumerate(incorporated_clarifications, 1):
            lines.append(f"{index}. {sentence}")

    chronology_lines = [
        _clean_sentence(item)
        for item in _listify(draft.get("anchored_chronology_summary"))
        if _clean_text(item)
    ]
    if chronology_lines:
        _append_blank()
        lines.append("ANCHORED CHRONOLOGY")
        for index, chronology_line in enumerate(chronology_lines, 1):
            lines.append(f"{index}. {chronology_line}")

    claims = _listify(draft.get("legal_claims")) or _listify(draft.get("claims_for_relief"))
    if claims:
        _append_blank()
        lines.append("CLAIMS FOR RELIEF")
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        _append_blank()
        lines.append(str(claim.get("title") or claim.get("count_title") or claim.get("claim_name") or "Claim"))
        if claim.get("description"):
            lines.append(_clean_sentence(claim.get("description")))
        if claim.get("legal_standard"):
            lines.append("Legal Standard:")
            lines.append(_clean_sentence(claim.get("legal_standard")))
        for item in _listify(claim.get("legal_standard_elements")):
            if not isinstance(item, dict):
                continue
            element_text = _clean_sentence(item.get("element") or item.get("description"))
            citation = str(item.get("citation") or "").strip()
            if citation and element_text:
                lines.append(f"- {element_text} ({citation})")
            elif element_text:
                lines.append(f"- {element_text}")

        supporting_facts = [_clean_sentence(fact) for fact in _listify(claim.get("supporting_facts")) if _clean_text(fact)]
        if supporting_facts:
            lines.append("Supporting Facts:")
            for fact in supporting_facts:
                lines.append(f"- {fact}")
            rows = _claim_rows(claim)
            if rows:
                row_lookup = {}
                for row in rows:
                    text_key = _clean_text(row.get("text") or "").lower()
                    if text_key and text_key not in row_lookup:
                        row_lookup[text_key] = row
                for fact in supporting_facts:
                    row = row_lookup.get(_clean_text(fact).rstrip(".").lower())
                    if not isinstance(row, dict):
                        row = row_lookup.get(_clean_text(fact).lower())
                    if not isinstance(row, dict):
                        continue
                    trace_parts = []
                    fact_ids = _format_id_list(row.get("fact_ids"), prefix="fact ids: ")
                    trace_ids = _format_id_list(row.get("support_trace_ids"), prefix="trace ids: ")
                    artifact_ids = _format_id_list(row.get("source_artifact_ids"), prefix="artifact ids: ")
                    if fact_ids:
                        trace_parts.append(fact_ids)
                    if trace_ids:
                        trace_parts.append(trace_ids)
                    if artifact_ids:
                        trace_parts.append(artifact_ids)
                    if trace_parts:
                        lines.append(f"  Support Trace: {'; '.join(trace_parts)}")

        authorities = _listify(claim.get("supporting_authorities"))
        if authorities:
            lines.append("Supporting Authorities:")
            for authority in authorities:
                if not isinstance(authority, dict):
                    continue
                authority_line = authority.get("citation") or authority.get("title") or "Authority"
                if authority.get("title") and authority.get("citation"):
                    authority_line = f"{authority['citation']} - {authority['title']}"
                lines.append(f"- {_clean_text(authority_line)}")

        missing_requirements = [item for item in _listify(claim.get("missing_requirements")) if isinstance(item, dict)]
        if missing_requirements:
            lines.append("Unresolved Gaps:")
            for requirement in missing_requirements:
                name = _clean_text(requirement.get("name") or "Gap")
                citation = _clean_text(requirement.get("citation") or "")
                action = _clean_text(requirement.get("suggested_action") or "")
                if citation and action:
                    lines.append(f"- {name} ({citation}): {action}")
                elif citation:
                    lines.append(f"- {name} ({citation})")
                elif action:
                    lines.append(f"- {name}: {action}")
                else:
                    lines.append(f"- {name}")

        supporting_exhibits = _listify(claim.get("supporting_exhibits"))
        if supporting_exhibits:
            exhibit_labels = ", ".join(exhibit.get("label", "") for exhibit in supporting_exhibits if isinstance(exhibit, dict) and exhibit.get("label"))
            if exhibit_labels:
                lines.append(f"Exhibits Incorporated by Reference: {exhibit_labels}.")

    _append_blank()
    lines.append("PRAYER FOR RELIEF")
    for item in _listify(draft.get("requested_relief")):
        lines.append(f"- {_clean_sentence(item)}")

    jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
    if jury_demand:
        _append_blank()
        lines.append(str(jury_demand.get("title") or "JURY DEMAND").upper())
        if jury_demand.get("text"):
            lines.append(_clean_sentence(jury_demand.get("text")))

    exhibits = [item for item in _listify(draft.get("exhibits")) if isinstance(item, dict)]
    if exhibits:
        _append_blank()
        lines.append("EXHIBITS")
        for exhibit in exhibits:
            reference = _clean_text(exhibit.get("reference") or exhibit.get("source_url") or exhibit.get("cid") or "")
            summary = _clean_text(exhibit.get("summary") or exhibit.get("description") or "")
            title = _clean_text(exhibit.get("title") or exhibit.get("description") or "Supporting exhibit")
            exhibit_line = f"{exhibit.get('label', 'Exhibit')} - {title}"
            context_parts: List[str] = []
            if reference:
                context_parts.append(reference)
            modality = _clean_text(exhibit.get("type") or exhibit.get("source_kind") or "")
            if modality in {"policy_document", "file_evidence"}:
                context_parts.append(f"modality: {modality}")
            if context_parts:
                exhibit_line = f"{exhibit_line} ({'; '.join(context_parts)})"
            lines.append(exhibit_line)
            if summary:
                lines.append(f"  {_clean_sentence(summary)}")
            exhibit_fact_ids = _format_id_list(exhibit.get("fact_ids") or exhibit.get("canonical_fact_ids"), prefix="fact ids: ")
            exhibit_trace_ids = _format_id_list(exhibit.get("support_trace_ids"), prefix="trace ids: ")
            if exhibit_fact_ids or exhibit_trace_ids:
                trace_parts = [item for item in [exhibit_fact_ids, exhibit_trace_ids] if item]
                lines.append(f"  Support Trace: {'; '.join(trace_parts)}")

    drafting_readiness = draft.get("drafting_readiness", {}) if isinstance(draft.get("drafting_readiness"), dict) else {}
    document_provenance_summary = (
        draft.get("document_provenance_summary", {})
        if isinstance(draft.get("document_provenance_summary"), dict)
        else {}
    )
    if drafting_readiness or document_provenance_summary:
        _append_blank()
        lines.append("DRAFTING READINESS")
        if drafting_readiness:
            lines.append(f"Status: {_clean_text(drafting_readiness.get('status') or 'unknown').upper() or 'UNKNOWN'}")
            warning_count = drafting_readiness.get("warning_count")
            if warning_count not in (None, ""):
                lines.append(f"Warning count: {int(warning_count)}")
            for section in _listify(drafting_readiness.get("sections")):
                if not isinstance(section, dict):
                    continue
                section_title = _clean_text(section.get("title") or section.get("name") or "")
                section_status = _clean_text(section.get("status") or "")
                if section_title and section_status:
                    lines.append(f"- {section_title}: {section_status}")
        if document_provenance_summary:
            ratio = document_provenance_summary.get("fact_backed_ratio")
            if ratio is not None:
                lines.append(f"Fact-backed ratio: {float(ratio):.2f}")
            summary_fact_backed = int(document_provenance_summary.get("summary_fact_backed_count") or 0)
            summary_fact_total = int(document_provenance_summary.get("summary_fact_count") or 0)
            claim_fact_backed = int(document_provenance_summary.get("claim_supporting_fact_backed_count") or 0)
            claim_fact_total = int(document_provenance_summary.get("claim_supporting_fact_count") or 0)
            lines.append(f"Summary facts grounded: {summary_fact_backed}/{summary_fact_total}")
            lines.append(f"Claim support grounded: {claim_fact_backed}/{claim_fact_total}")
            if document_provenance_summary.get("low_grounding_flag"):
                lines.append("Grounding warning: canonical fact and artifact support should be increased before filing.")

    explicit_anchor_markers = " ".join(lines).lower()
    unresolved_anchor_questions: List[str] = []
    if "grievance_hearing" not in explicit_anchor_markers and "grievance hearing" not in explicit_anchor_markers:
        unresolved_anchor_questions.append("What grievance hearing request was made, when was it made, and who responded on behalf of HACC?")
    if "appeal_rights" not in explicit_anchor_markers and "appeal rights" not in explicit_anchor_markers:
        unresolved_anchor_questions.append("What appeal rights notice was provided, on what date, and by which HACC actor?")
    if unresolved_anchor_questions:
        _append_blank()
        lines.append("UNRESOLVED FACTUAL OR LEGAL GAPS BEFORE FORMALIZATION")
        for index, question in enumerate(unresolved_anchor_questions, 1):
            lines.append(f"{index}. {_clean_sentence(question)}")

    affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
    if affidavit:
        _append_blank()
        lines.append(str(affidavit.get("title") or "AFFIDAVIT IN SUPPORT OF COMPLAINT").upper())
        for venue_line in _listify(affidavit.get("venue_lines")):
            cleaned_venue_line = _clean_text(venue_line)
            if cleaned_venue_line:
                lines.append(cleaned_venue_line)
        if affidavit.get("intro"):
            lines.append(_clean_sentence(affidavit.get("intro")))
        if affidavit.get("knowledge_graph_note"):
            lines.append(_clean_sentence(affidavit.get("knowledge_graph_note")))
        if affidavit.get("facts"):
            lines.append("Affiant states as follows:")
            for index, fact in enumerate(_listify(affidavit.get("facts")), 1):
                cleaned_fact = _clean_sentence(fact)
                if cleaned_fact:
                    lines.append(f"{index}. {cleaned_fact}")
        for exhibit in _listify(affidavit.get("supporting_exhibits")):
            if not isinstance(exhibit, dict):
                continue
            exhibit_line = f"{exhibit.get('label', 'Exhibit')} - {_clean_text(exhibit.get('title') or 'Supporting exhibit')}"
            if exhibit.get("link"):
                exhibit_line = f"{exhibit_line} ({exhibit['link']})"
            lines.append(exhibit_line)
        if affidavit.get("dated"):
            lines.append(str(affidavit["dated"]))
        if affidavit.get("signature_line"):
            lines.append(str(affidavit["signature_line"]))
        if affidavit.get("jurat"):
            lines.append(str(affidavit["jurat"]))
        for notary_line in _listify(affidavit.get("notary_block")):
            cleaned_notary_line = _clean_text(notary_line)
            if cleaned_notary_line:
                lines.append(cleaned_notary_line)

    verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
    if verification:
        _append_blank()
        lines.append(str(verification.get("title") or "VERIFICATION").upper())
        if verification.get("text"):
            lines.append(_clean_sentence(verification.get("text")))
        if verification.get("dated"):
            lines.append(str(verification["dated"]))
        if verification.get("signature_line"):
            lines.append(str(verification["signature_line"]))

    certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
    if certificate_of_service:
        _append_blank()
        lines.append(str(certificate_of_service.get("title") or "CERTIFICATE OF SERVICE").upper())
        if certificate_of_service.get("text"):
            lines.append(_clean_sentence(certificate_of_service.get("text")))
        for detail_line in _listify(certificate_of_service.get("detail_lines")):
            if detail_line:
                lines.append(str(detail_line))
        if certificate_of_service.get("dated"):
            lines.append(str(certificate_of_service["dated"]))
        if certificate_of_service.get("signature_line"):
            lines.append(str(certificate_of_service["signature_line"]))

    signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
    _append_blank()
    lines.append("SIGNATURE BLOCK")
    lines.append("Respectfully submitted,")
    lines.extend(self._signature_block_lines(signature_block))
    return "\n".join(line for line in lines if line is not None)


def build(
    self,
    *,
    court_name: Optional[str] = None,
    district: Optional[str] = None,
    county: Optional[str] = None,
    division: Optional[str] = None,
    court_header_override: Optional[str] = None,
    case_number: Optional[str] = None,
    lead_case_number: Optional[str] = None,
    related_case_number: Optional[str] = None,
    assigned_judge: Optional[str] = None,
    courtroom: Optional[str] = None,
    title_override: Optional[str] = None,
    plaintiff_names: Optional[List[str]] = None,
    defendant_names: Optional[List[str]] = None,
    requested_relief: Optional[List[str]] = None,
    jury_demand: Optional[bool] = None,
    jury_demand_text: Optional[str] = None,
    signer_name: Optional[str] = None,
    signer_title: Optional[str] = None,
    signer_firm: Optional[str] = None,
    signer_bar_number: Optional[str] = None,
    signer_contact: Optional[str] = None,
    additional_signers: Optional[List[Dict[str, str]]] = None,
    declarant_name: Optional[str] = None,
    service_method: Optional[str] = None,
    service_recipients: Optional[List[str]] = None,
    service_recipient_details: Optional[List[Dict[str, str]]] = None,
    signature_date: Optional[str] = None,
    verification_date: Optional[str] = None,
    service_date: Optional[str] = None,
    affidavit_title: Optional[str] = None,
    affidavit_intro: Optional[str] = None,
    affidavit_facts: Optional[List[str]] = None,
    affidavit_supporting_exhibits: Optional[List[Dict[str, str]]] = None,
    affidavit_include_complaint_exhibits: Optional[bool] = None,
    affidavit_venue_lines: Optional[List[str]] = None,
    affidavit_jurat: Optional[str] = None,
    affidavit_notary_block: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    base_formal_complaint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    phase_manager = getattr(self.mediator, "phase_manager", None)
    kg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph") if phase_manager else None
    dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph") if phase_manager else None
    intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") if phase_manager else None
    legal_graph = phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, "legal_graph") if phase_manager else None
    matching_results = phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, "matching_results") if phase_manager else None

    resolved_user_id = user_id or getattr(self.mediator.state, "username", None) or getattr(self.mediator.state, "hashed_username", None) or "anonymous"
    base = dict(base_formal_complaint or {})
    evidence_records = self._safe_call("get_user_evidence", resolved_user_id, default=[])
    authority_records = self._safe_call("get_legal_authorities", resolved_user_id, default=[])
    support_links = self._safe_call("get_claim_support", resolved_user_id, default=[])
    intake_summary = self._collect_intake_summary()
    parties = self._build_parties(
        kg,
        base.get("parties"),
        plaintiff_names=plaintiff_names,
        defendant_names=defendant_names,
    )
    jurisdiction = str(base.get("jurisdiction") or self._infer_jurisdiction(legal_graph) or "federal")
    caption = self._build_caption(
        parties=parties,
        jurisdiction=jurisdiction,
        court_name=court_name,
        district=district,
        county=county,
        division=division,
        court_header_override=court_header_override,
        case_number=case_number,
        lead_case_number=lead_case_number,
        related_case_number=related_case_number,
        assigned_judge=assigned_judge,
        courtroom=courtroom,
        title=title_override or str(base.get("title") or "").strip(),
    )
    factual_allegations = self._build_factual_allegations(
        base.get("factual_allegations"),
        kg,
        intake_summary,
    )
    exhibits = self._build_exhibits(evidence_records, support_links)
    claims = self._build_claims(
        matching_results=matching_results,
        dependency_graph=dg,
        legal_graph=legal_graph,
        authority_records=authority_records,
        exhibits=exhibits,
        factual_allegations=factual_allegations,
        user_id=resolved_user_id,
    )
    requested_relief = self._build_requested_relief(requested_relief or base.get("prayer_for_relief"))
    jury_demand_block = self._build_jury_demand(jury_demand=jury_demand, jury_demand_text=jury_demand_text)
    caption["jury_demand_notice"] = "JURY TRIAL DEMANDED" if jury_demand_block else None
    nature_of_action = self._build_nature_of_action(base.get("statement_of_claim"), claims)
    jurisdiction_statement = self._build_jurisdiction_statement(jurisdiction, authority_records)
    venue_statement = self._build_venue_statement(district, county, division, jurisdiction)
    signature_block = self._build_signature_block(
        parties,
        signer_name=signer_name,
        signer_title=signer_title,
        signer_firm=signer_firm,
        signer_bar_number=signer_bar_number,
        signer_contact=signer_contact,
        additional_signers=additional_signers,
        signature_date=signature_date,
    )
    verification = self._build_verification(
        parties,
        declarant_name=declarant_name,
        signer_name=signer_name,
        verification_date=verification_date,
    )
    certificate_of_service = self._build_certificate_of_service(
        parties,
        signer_name=signer_name,
        service_method=service_method,
        service_recipients=service_recipients,
        service_recipient_details=service_recipient_details,
        service_date=service_date,
        jurisdiction=jurisdiction,
    )
    affidavit = self._build_affidavit(
        parties=parties,
        caption=caption,
        factual_allegations=factual_allegations,
        claims=claims,
        exhibits=exhibits,
        verification=verification,
        signature_block=signature_block,
        affidavit_overrides=self._build_affidavit_overrides(
            affidavit_title=affidavit_title,
            affidavit_intro=affidavit_intro,
            affidavit_facts=affidavit_facts,
            affidavit_supporting_exhibits=affidavit_supporting_exhibits,
            affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
            affidavit_venue_lines=affidavit_venue_lines,
            affidavit_jurat=affidavit_jurat,
            affidavit_notary_block=affidavit_notary_block,
        ),
    )
    legal_standards = [
        {
            "claim_name": claim.get("claim_name", ""),
            "claim_type": claim.get("claim_type", ""),
            "standard": claim.get("legal_standard", ""),
            "citations": [
                item.get("citation", "")
                for item in claim.get("legal_standard_elements", [])
                if item.get("citation")
            ],
        }
        for claim in claims
    ]
    anchored_chronology_summary = _build_anchored_chronology_summary(
        intake_case_file if isinstance(intake_case_file, dict) else {}
    )

    draft = {
        **base,
        "generated_at": _utc_now_isoformat(),
        "court_header": caption["court_header"],
        "caption": caption,
        "case_number": caption["case_number"],
        "title": caption["case_title"],
        "parties": parties,
        "nature_of_action": nature_of_action,
        "jurisdiction": jurisdiction,
        "jurisdiction_statement": jurisdiction_statement,
        "venue_statement": venue_statement,
        "statement_of_claim": str(base.get("statement_of_claim") or nature_of_action),
        "summary_of_facts": factual_allegations[: min(len(factual_allegations), 6)],
        "factual_allegations": factual_allegations,
        "factual_allegation_groups": _build_factual_allegation_groups(factual_allegations),
        "anchored_chronology_summary": anchored_chronology_summary,
        "legal_standards": legal_standards,
        "legal_claims": claims,
        "claims_for_relief": claims,
        "prayer_for_relief": requested_relief,
        "requested_relief": requested_relief,
        "jury_demand": jury_demand_block,
        "supporting_documents": exhibits,
        "exhibits": exhibits,
        "supporting_exhibits": exhibits,
        "intake_summary": intake_summary,
        "signature_block": signature_block,
        "verification": verification,
        "certificate_of_service": certificate_of_service,
        "affidavit": affidavit,
    }
    draft["draft_text"] = self.render_text(draft)
    return draft


def _write_docx(self, draft: Dict[str, Any], destination: Path) -> None:
    if not HAS_DOCX:
        raise RuntimeError("DOCX export requires python-docx to be installed")
    document = DocxDocument()
    normal_style = document.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style.font.size = Pt(12)

    for line in [draft.get("court_header"), draft.get("caption", {}).get("division_line")]:
        if not line:
            continue
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(str(line))
        run.bold = True

    caption = draft.get("caption", {}) if isinstance(draft.get("caption"), dict) else {}
    table = document.add_table(rows=1, cols=2)
    table.columns[0].width = Inches(4.75)
    table.columns[1].width = Inches(2.0)
    resolved_case_number = caption.get("case_number") or draft.get("case_number") or "________________"
    table.cell(0, 0).text = "\n".join(build_caption_party_block_lines(draft.get("parties", {})))
    table.cell(0, 1).text = "\n".join(
        build_case_detail_lines({"case_number": resolved_case_number, **caption})
    )

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("COMPLAINT").bold = True
    if caption.get("jury_demand_notice"):
        jury_notice = document.add_paragraph()
        jury_notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
        jury_notice.add_run(str(caption["jury_demand_notice"])).bold = True

    self._docx_section(document, "Nature of the Action", [draft.get("nature_of_action")])
    party_lines = []
    for plaintiff in draft.get("parties", {}).get("plaintiffs", []):
        party_lines.append(f"Plaintiff {plaintiff} is an aggrieved party bringing this action.")
    for defendant in draft.get("parties", {}).get("defendants", []):
        party_lines.append(f"Defendant {defendant} is alleged to be responsible for the conduct described below.")
    self._docx_section(document, "Parties", party_lines)
    self._docx_section(document, "Jurisdiction and Venue", [draft.get("jurisdiction_statement"), draft.get("venue_statement")])
    allegation_groups = draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else []
    if allegation_groups:
        heading_paragraph = document.add_paragraph()
        heading_paragraph.add_run("Factual Allegations").bold = True
        for group in allegation_groups:
            if not isinstance(group, dict):
                continue
            if group.get("title"):
                group_heading = document.add_paragraph()
                group_heading.add_run(str(group["title"])).italic = True
            for entry in _listify(group.get("paragraphs")):
                if not isinstance(entry, dict):
                    continue
                text = _clean_sentence(entry.get("text"))
                if text:
                    document.add_paragraph(f"{entry.get('number')}. {text}")
    else:
        self._docx_section(document, "Factual Allegations", draft.get("factual_allegations", []), numbered=True)

    chronology_lines = [
        _clean_sentence(item)
        for item in _listify(draft.get("anchored_chronology_summary"))
        if _clean_text(item)
    ]
    if chronology_lines:
        self._docx_section(document, "Anchored Chronology", chronology_lines, numbered=True)

    claims_heading = document.add_paragraph()
    claims_heading.add_run("Claims for Relief").bold = True
    for claim in _listify(draft.get("legal_claims")):
        claim_heading = document.add_paragraph()
        claim_heading.add_run(str(claim.get("title") or "Claim")).bold = True
        if claim.get("description"):
            document.add_paragraph(_clean_sentence(claim.get("description")))
        if claim.get("legal_standard"):
            paragraph = document.add_paragraph()
            paragraph.add_run("Legal Standard: ").bold = True
            paragraph.add_run(_clean_sentence(claim.get("legal_standard")))
        for item in _listify(claim.get("legal_standard_elements")):
            paragraph = document.add_paragraph(style="List Bullet")
            text = _clean_sentence(item.get("element") or "")
            citation = _clean_text(item.get("citation") or "")
            paragraph.add_run(f"{text} ({citation})" if citation else text)
        for fact in _listify(claim.get("supporting_facts")):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.add_run(_clean_sentence(fact))
        exhibit_labels = ", ".join(exhibit.get("label", "") for exhibit in _listify(claim.get("supporting_exhibits")) if exhibit.get("label"))
        if exhibit_labels:
            document.add_paragraph(f"Supported by {exhibit_labels}.")

    self._docx_section(document, "Prayer for Relief", draft.get("requested_relief", []), bulleted=True)
    jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
    if jury_demand:
        self._docx_section(document, jury_demand.get("title") or "Jury Demand", [jury_demand.get("text")])
    exhibit_lines = []
    for exhibit in _listify(draft.get("exhibits")):
        line = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
        if exhibit.get("reference"):
            line = f"{line} ({exhibit['reference']})"
        exhibit_lines.append(line)
    self._docx_section(document, "Exhibits", exhibit_lines)
    affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
    if affidavit:
        affidavit_lines = list(_listify(affidavit.get("venue_lines"))) + [affidavit.get("intro"), affidavit.get("knowledge_graph_note")]
        affidavit_lines.extend(
            f"{index}. {_clean_sentence(fact)}"
            for index, fact in enumerate(_listify(affidavit.get("facts")), 1)
            if _clean_text(fact)
        )
        affidavit_lines.extend(
            f"{exhibit.get('label', 'Exhibit')} - {_clean_text(exhibit.get('title') or 'Supporting exhibit')}"
            + (f" ({exhibit['link']})" if exhibit.get("link") else "")
            for exhibit in _listify(affidavit.get("supporting_exhibits"))
            if isinstance(exhibit, dict)
        )
        affidavit_lines.extend([affidavit.get("dated"), affidavit.get("signature_line"), affidavit.get("jurat")])
        affidavit_lines.extend(_listify(affidavit.get("notary_block")))
        self._docx_section(document, affidavit.get("title") or "Affidavit in Support of Complaint", affidavit_lines)
    verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
    if verification:
        self._docx_section(
            document,
            verification.get("title") or "Verification",
            [verification.get("text"), verification.get("dated"), verification.get("signature_line")],
        )
    certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
    if certificate_of_service:
        self._docx_section(
            document,
            certificate_of_service.get("title") or "Certificate of Service",
            [certificate_of_service.get("text")]
            + _listify(certificate_of_service.get("detail_lines"))
            + [certificate_of_service.get("dated"), certificate_of_service.get("signature_line")],
        )
    signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
    self._docx_section(
        document,
        "Signature Block",
        ["Respectfully submitted,", *self._signature_block_lines(signature_block)],
    )
    document.save(str(destination))


def _write_pdf(self, draft: Dict[str, Any], destination: Path) -> None:
    if not HAS_REPORTLAB:
        raise RuntimeError("PDF export requires reportlab to be installed")
    caption = draft.get("caption", {}) if isinstance(draft.get("caption"), dict) else {}
    styles = getSampleStyleSheet()
    centered = ParagraphStyle("ComplaintCentered", parent=styles["Heading2"], alignment=TA_CENTER)
    section = ParagraphStyle("ComplaintSection", parent=styles["Heading3"], spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("ComplaintBody", parent=styles["BodyText"], leading=15)
    story = []
    story.append(Paragraph(str(draft.get("court_header") or "IN THE COURT OF COMPETENT JURISDICTION"), centered))
    if caption.get("division_line"):
        story.append(Paragraph(str(caption["division_line"]), centered))
    story.append(Spacer(1, 0.2 * inch))

    story.append(
        build_case_caption_table(
            draft.get("parties", {}),
            {"case_number": draft.get("case_number") or caption.get("case_number"), **caption},
            body,
            left_width=4.5 * inch,
            right_width=2.0 * inch,
        )
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("COMPLAINT", centered))
    if caption.get("jury_demand_notice"):
        story.append(Paragraph(str(caption["jury_demand_notice"]), centered))

    self._pdf_section(story, section, body, "Nature of the Action", [draft.get("nature_of_action")])
    party_lines = []
    for plaintiff in draft.get("parties", {}).get("plaintiffs", []):
        party_lines.append(f"Plaintiff {plaintiff} is an aggrieved party bringing this action.")
    for defendant in draft.get("parties", {}).get("defendants", []):
        party_lines.append(f"Defendant {defendant} is alleged to be responsible for the conduct described below.")
    self._pdf_section(story, section, body, "Parties", party_lines)
    self._pdf_section(story, section, body, "Jurisdiction and Venue", [draft.get("jurisdiction_statement"), draft.get("venue_statement")])
    allegation_groups = draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else []
    if allegation_groups:
        story.append(Paragraph("Factual Allegations", section))
        for group in allegation_groups:
            if not isinstance(group, dict):
                continue
            if group.get("title"):
                story.append(Paragraph(str(group["title"]), body))
            for entry in _listify(group.get("paragraphs")):
                if not isinstance(entry, dict):
                    continue
                text = _clean_sentence(entry.get("text"))
                if text:
                    story.append(Paragraph(f"{entry.get('number')}. {text}", body))
    else:
        self._pdf_section(story, section, body, "Factual Allegations", draft.get("factual_allegations", []), numbered=True)

    chronology_lines = [
        _clean_sentence(item)
        for item in _listify(draft.get("anchored_chronology_summary"))
        if _clean_text(item)
    ]
    if chronology_lines:
        self._pdf_section(story, section, body, "Anchored Chronology", chronology_lines, numbered=True)

    story.append(Paragraph("Claims for Relief", section))
    for claim in _listify(draft.get("legal_claims")):
        story.append(Paragraph(str(claim.get("title") or "Claim"), section))
        if claim.get("description"):
            story.append(Paragraph(_clean_sentence(claim.get("description")), body))
        if claim.get("legal_standard"):
            story.append(Paragraph(f"<b>Legal Standard:</b> {_clean_sentence(claim.get('legal_standard'))}", body))
        for item in _listify(claim.get("legal_standard_elements")):
            text = _clean_sentence(item.get("element") or "")
            citation = _clean_text(item.get("citation") or "")
            story.append(Paragraph(f"• {text} ({citation})" if citation else f"• {text}", body))
        for fact in _listify(claim.get("supporting_facts")):
            story.append(Paragraph(f"• {_clean_sentence(fact)}", body))
        exhibit_labels = ", ".join(exhibit.get("label", "") for exhibit in _listify(claim.get("supporting_exhibits")) if exhibit.get("label"))
        if exhibit_labels:
            story.append(Paragraph(f"Supported by {exhibit_labels}.", body))

    self._pdf_section(story, section, body, "Prayer for Relief", draft.get("requested_relief", []), bulleted=True)
    jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
    if jury_demand:
        self._pdf_section(story, section, body, jury_demand.get("title") or "Jury Demand", [jury_demand.get("text")])
    exhibit_lines = []
    for exhibit in _listify(draft.get("exhibits")):
        line = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
        if exhibit.get("reference"):
            line = f"{line} ({exhibit['reference']})"
        exhibit_lines.append(line)
    self._pdf_section(story, section, body, "Exhibits", exhibit_lines)
    affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
    if affidavit:
        affidavit_lines = list(_listify(affidavit.get("venue_lines"))) + [affidavit.get("intro"), affidavit.get("knowledge_graph_note")]
        affidavit_lines.extend(
            f"{index}. {_clean_sentence(fact)}"
            for index, fact in enumerate(_listify(affidavit.get("facts")), 1)
            if _clean_text(fact)
        )
        affidavit_lines.extend(
            f"{exhibit.get('label', 'Exhibit')} - {_clean_text(exhibit.get('title') or 'Supporting exhibit')}"
            + (f" ({exhibit['link']})" if exhibit.get("link") else "")
            for exhibit in _listify(affidavit.get("supporting_exhibits"))
            if isinstance(exhibit, dict)
        )
        affidavit_lines.extend([affidavit.get("dated"), affidavit.get("signature_line"), affidavit.get("jurat")])
        affidavit_lines.extend(_listify(affidavit.get("notary_block")))
        self._pdf_section(story, section, body, affidavit.get("title") or "Affidavit in Support of Complaint", affidavit_lines)
    verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
    if verification:
        self._pdf_section(
            story,
            section,
            body,
            verification.get("title") or "Verification",
            [verification.get("text"), verification.get("dated"), verification.get("signature_line")],
        )
    certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
    if certificate_of_service:
        self._pdf_section(
            story,
            section,
            body,
            certificate_of_service.get("title") or "Certificate of Service",
            [certificate_of_service.get("text")]
            + _listify(certificate_of_service.get("detail_lines"))
            + [certificate_of_service.get("dated"), certificate_of_service.get("signature_line")],
        )
    signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
    self._pdf_section(
        story,
        section,
        body,
        "Signature Block",
        ["Respectfully submitted,", *self._signature_block_lines(signature_block)],
    )
    document = SimpleDocTemplate(str(destination), pagesize=letter)
    footer = make_page_footer_renderer("Complaint")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
