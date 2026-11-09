"""Rendering methods delegated from FormalComplaintDocumentBuilder."""

from __future__ import annotations

from complaint_phases.document_pipeline import (
    _coerce_bool,
    _coerce_list,
    _dedupe_text_values,
    _merge_status,
    _roman,
    _safe_float,
    build_workflow_phase_plan,
    escape,
)


def _build_runtime_workflow_phase_plan(
    self,
    *,
    drafting_readiness: Dict[str, Any],
    document_optimization: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    phase_manager = getattr(self.mediator, "phase_manager", None)
    optimization_report = document_optimization if isinstance(document_optimization, dict) else {}
    if phase_manager is None and not optimization_report:
        return {}

    phases: Dict[str, Dict[str, Any]] = {}
    actor_critic_guidance = self._extract_actor_critic_guidance(optimization_report)
    adversarial_flow_signals = self._extract_adversarial_session_flow_signals(optimization_report)
    graph_phase = self._build_graph_analysis_phase_guidance(
        phase_manager,
        document_optimization=optimization_report,
    )
    if graph_phase:
        phases["graph_analysis"] = graph_phase

    document_phase = self._build_document_generation_phase_guidance(
        drafting_readiness=drafting_readiness,
        document_optimization=optimization_report,
    )
    graph_status = str(graph_phase.get("status") or "ready").strip().lower() if graph_phase else "ready"
    graph_signals = (
        dict(graph_phase.get("signals") or {})
        if isinstance(graph_phase.get("signals"), dict)
        else {}
    )
    readiness_graph_signals = (
        dict(drafting_readiness.get("graph_completeness_signals") or {})
        if isinstance(drafting_readiness.get("graph_completeness_signals"), dict)
        else {}
    )
    unresolved_factual_gaps = [
        str(item).strip()
        for item in list(drafting_readiness.get("unresolved_factual_gaps") or [])
        if str(item).strip()
    ]
    unresolved_legal_gaps = [
        str(item).strip()
        for item in list(drafting_readiness.get("unresolved_legal_gaps") or [])
        if str(item).strip()
    ]
    uncovered_intake_objectives = [
        str(item).strip()
        for item in list(drafting_readiness.get("uncovered_intake_objectives") or [])
        if str(item).strip()
    ]
    missing_required_intake_objectives = [
        str(item).strip()
        for item in list(drafting_readiness.get("missing_required_intake_objectives") or [])
        if str(item).strip()
    ]
    structured_handoff_signals = (
        dict(drafting_readiness.get("structured_intake_handoff_signals") or {})
        if isinstance(drafting_readiness.get("structured_intake_handoff_signals"), dict)
        else {}
    )
    structured_handoff_gap_count = int(structured_handoff_signals.get("gap_count", 0) or 0)
    weak_complaint_types = [
        str(item).strip()
        for item in list(drafting_readiness.get("weak_complaint_types") or [])
        if str(item).strip()
    ]
    weak_evidence_modalities = [
        str(item).strip()
        for item in list(drafting_readiness.get("weak_evidence_modalities") or [])
        if str(item).strip()
    ]
    targeted_weak_complaint_types = [
        item
        for item in weak_complaint_types
        if item.lower() in {"housing_discrimination", "hacc_research_engine"}
    ]
    targeted_weak_evidence_modalities = [
        item
        for item in weak_evidence_modalities
        if item.lower() in {"policy_document", "file_evidence"}
    ]
    graph_remaining_gap_count = max(
        int(graph_signals.get("remaining_gap_count", 0) or 0),
        int(graph_signals.get("current_gap_count", 0) or 0),
        int(readiness_graph_signals.get("remaining_gap_count", 0) or 0),
        int(readiness_graph_signals.get("current_gap_count", 0) or 0),
    )
    graph_gate_active = (
        graph_status != "ready"
        or graph_remaining_gap_count > 0
        or not _coerce_bool(
            readiness_graph_signals.get("knowledge_graph_available", graph_signals.get("knowledge_graph_available", True)),
            default=True,
        )
        or not _coerce_bool(
            readiness_graph_signals.get("dependency_graph_available", graph_signals.get("dependency_graph_available", True)),
            default=True,
        )
        )
    if document_phase:
        updated_document_phase = dict(document_phase)
        actions = [str(item).strip() for item in list(updated_document_phase.get("recommended_actions") or []) if str(item).strip()]
        handoff_gap_active = bool(
            unresolved_factual_gaps
            or unresolved_legal_gaps
            or uncovered_intake_objectives
            or missing_required_intake_objectives
            or structured_handoff_gap_count > 0
            or targeted_weak_complaint_types
            or targeted_weak_evidence_modalities
        )
        if graph_gate_active:
            gate_status = "blocked"
            updated_document_phase["status"] = _merge_status(
                str(updated_document_phase.get("status") or "ready"),
                gate_status,
            )
            summary = str(updated_document_phase.get("summary") or "").strip()
            gate_summary = (
                "Document generation is gated on graph completeness and should not be treated as final until graph blockers are resolved."
            )
            updated_document_phase["summary"] = f"{summary} {gate_summary}".strip()
            actions.append(
                "Resolve graph completeness blockers (knowledge/dependency graph availability and unresolved graph gaps) before formalization."
            )
        if handoff_gap_active:
            updated_document_phase["status"] = _merge_status(
                str(updated_document_phase.get("status") or "ready"),
                "warning",
            )
            summary = str(updated_document_phase.get("summary") or "").strip()
            handoff_summary = (
                "Drafting handoff still has unresolved factual/legal/objective gaps that should be closed before formalization."
            )
            updated_document_phase["summary"] = f"{summary} {handoff_summary}".strip()
        if unresolved_factual_gaps:
            actions.append(
                "Close unresolved factual gaps before formalization: "
                + "; ".join(unresolved_factual_gaps[:3])
            )
        if unresolved_legal_gaps:
            actions.append(
                "Close unresolved legal gaps before formalization: "
                + "; ".join(unresolved_legal_gaps[:3])
            )
        if uncovered_intake_objectives or missing_required_intake_objectives:
            actions.append(
                "Resolve uncovered intake objectives before formalization: "
                + ", ".join((missing_required_intake_objectives or uncovered_intake_objectives)[:4])
            )
        if structured_handoff_gap_count > 0:
            actions.append(
                "Promote structured intake facts, date/actor anchors, and evidence references directly into summary-of-facts and claim-support paragraphs before document optimization runs."
            )
        if targeted_weak_complaint_types:
            actions.append(
                "Generalize drafting quality for weak complaint types before formalization: "
                + ", ".join(targeted_weak_complaint_types)
            )
        if targeted_weak_evidence_modalities:
            actions.append(
                "Strengthen allegation support for weak evidence modalities before formalization: "
                + ", ".join(targeted_weak_evidence_modalities)
            )
        if bool(adversarial_flow_signals.get("assessment_blocked")):
            gate_status = "blocked" if str(drafting_readiness.get("phase_status") or "").strip().lower() == "critical" else "warning"
            updated_document_phase["status"] = _merge_status(
                str(updated_document_phase.get("status") or "ready"),
                gate_status,
            )
            summary = str(updated_document_phase.get("summary") or "").strip()
            session_summary = (
                "No successful adversarial sessions were available to assess drafting handoff quality."
            )
            updated_document_phase["summary"] = f"{summary} {session_summary}".strip()
            actions.append(
                "Restore a stable adversarial session flow before tuning document-generation handoffs."
            )
        updated_document_phase["recommended_actions"] = _dedupe_text_values(actions)
        signals = dict(updated_document_phase.get("signals") or {})
        signals["gate_on_graph_completeness"] = bool(graph_gate_active)
        signals["graph_phase_status"] = graph_status
        signals["graph_remaining_gap_count"] = int(graph_remaining_gap_count)
        signals["drafting_coverage"] = _safe_float(drafting_readiness.get("coverage"), 0.0)
        signals["drafting_phase_status"] = str(drafting_readiness.get("phase_status") or "ready").strip().lower() or "ready"
        signals["unresolved_factual_gap_count"] = len(unresolved_factual_gaps)
        signals["unresolved_legal_gap_count"] = len(unresolved_legal_gaps)
        signals["uncovered_intake_objective_count"] = len(uncovered_intake_objectives)
        signals["missing_required_intake_objective_count"] = len(missing_required_intake_objectives)
        signals["structured_intake_handoff_gap_count"] = int(structured_handoff_gap_count)
        signals["uncovered_intake_objectives"] = uncovered_intake_objectives[:8]
        signals["unresolved_factual_gaps"] = unresolved_factual_gaps[:6]
        signals["unresolved_legal_gaps"] = unresolved_legal_gaps[:6]
        signals["weak_complaint_types"] = weak_complaint_types
        signals["weak_evidence_modalities"] = weak_evidence_modalities
        signals["targeted_weak_complaint_types"] = targeted_weak_complaint_types
        signals["targeted_weak_evidence_modalities"] = targeted_weak_evidence_modalities
        signals["drafting_handoff_gap_active"] = bool(handoff_gap_active)
        signals["drafting_handoff_gap_count"] = (
            len(unresolved_factual_gaps)
            + len(unresolved_legal_gaps)
            + len(uncovered_intake_objectives)
            + len(missing_required_intake_objectives)
            + int(structured_handoff_gap_count > 0)
            + len(targeted_weak_complaint_types)
            + len(targeted_weak_evidence_modalities)
        )
        signals["ready_for_formalization"] = not bool(
            graph_gate_active
            or unresolved_factual_gaps
            or unresolved_legal_gaps
            or uncovered_intake_objectives
            or missing_required_intake_objectives
            or structured_handoff_gap_count > 0
            or targeted_weak_complaint_types
            or targeted_weak_evidence_modalities
        )
        signals["adversarial_session_flow_available"] = bool(adversarial_flow_signals.get("available"))
        signals["adversarial_session_count"] = int(adversarial_flow_signals.get("session_count") or 0)
        signals["adversarial_successful_session_count"] = int(
            adversarial_flow_signals.get("successful_session_count") or 0
        )
        signals["adversarial_session_flow_stable"] = not bool(adversarial_flow_signals.get("assessment_blocked"))
        updated_document_phase["signals"] = signals
        phases["document_generation"] = updated_document_phase
    intake_phase = self._build_intake_questioning_phase_guidance(
        drafting_readiness=drafting_readiness,
        document_optimization=optimization_report,
    )
    if intake_phase:
        phases["intake_questioning"] = intake_phase

    plan = build_workflow_phase_plan(phases)
    if not plan:
        return {}
    preferred_order = (
        list(actor_critic_guidance.get("phase_focus_order") or [])
        if actor_critic_guidance
        else ["graph_analysis", "document_generation", "intake_questioning"]
    )
    if bool(adversarial_flow_signals.get("assessment_blocked")):
        preferred_order = ["graph_analysis", "intake_questioning", "document_generation"]
    ordered = [name for name in preferred_order if name in phases]
    ordered.extend(
        name
        for name in list(plan.get("recommended_order") or [])
        if name in phases and name not in ordered
    )
    plan["recommended_order"] = ordered
    if actor_critic_guidance:
        plan["actor_critic_guidance"] = actor_critic_guidance
    return plan
def _render_docx(self, draft: Dict[str, Any], path: Path) -> None:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.opc.constants import RELATIONSHIP_TYPE
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor
    except ModuleNotFoundError:
        self._write_minimal_docx(path, self._build_minimal_docx_paragraphs(draft))
        return

    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    normal_style = document.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style.font.size = Pt(12)

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(draft.get("court_header", ""))
    run.bold = True
    run.font.size = Pt(12)

    case_caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
    caption_party_lines = case_caption.get("caption_party_lines") if isinstance(case_caption.get("caption_party_lines"), list) else self._build_caption_party_lines(case_caption)
    caption = document.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.add_run("\n\n".join(caption_party_lines) + "\n")

    case_no = document.add_paragraph()
    case_no.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    case_no.add_run(
        f"{case_caption.get('case_number_label', 'Civil Action No.')} {case_caption.get('case_number', '________________')}"
    ).bold = True
    if case_caption.get("lead_case_number"):
        lead_case = document.add_paragraph()
        lead_case.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        lead_case.add_run(
            f"{case_caption.get('lead_case_number_label', 'Lead Case No.')} {case_caption['lead_case_number']}"
        ).bold = True
    if case_caption.get("related_case_number"):
        related_case = document.add_paragraph()
        related_case.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        related_case.add_run(
            f"{case_caption.get('related_case_number_label', 'Related Case No.')} {case_caption['related_case_number']}"
        ).bold = True
    if case_caption.get("assigned_judge"):
        judge = document.add_paragraph()
        judge.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        judge.add_run(
            f"{case_caption.get('assigned_judge_label', 'Assigned Judge')}: {case_caption['assigned_judge']}"
        ).bold = True
    if case_caption.get("courtroom"):
        courtroom = document.add_paragraph()
        courtroom.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        courtroom.add_run(
            f"{case_caption.get('courtroom_label', 'Courtroom')}: {case_caption['courtroom']}"
        ).bold = True

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run(draft.get("case_caption", {}).get("document_title", "COMPLAINT"))
    title_run.bold = True
    title_run.font.size = Pt(14)
    if draft.get("case_caption", {}).get("jury_demand_notice"):
        jury_notice = document.add_paragraph()
        jury_notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
        jury_notice_run = jury_notice.add_run(draft["case_caption"]["jury_demand_notice"])
        jury_notice_run.bold = True
        jury_notice_run.font.size = Pt(12)

    self._add_docx_section(document, "Nature of the Action", draft.get("nature_of_action", []))
    self._add_docx_section(
        document,
        "Parties",
        [
            f"Plaintiff: {', '.join(draft.get('parties', {}).get('plaintiffs', []))}.",
            f"Defendant: {', '.join(draft.get('parties', {}).get('defendants', []))}.",
        ],
    )
    self._add_docx_section(
        document,
        "Jurisdiction and Venue",
        [draft.get("jurisdiction_statement"), draft.get("venue_statement")],
    )
    self._add_docx_numbered_facts(document, "Summary of Facts", draft.get("summary_of_facts", []))
    self._add_docx_numbered_facts(
        document,
        "Factual Allegations",
        draft.get("factual_allegations") or draft.get("summary_of_facts", []),
        groups=draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else None,
    )
    chronology_lines = draft.get("anchored_chronology_summary", [])
    if chronology_lines:
        self._add_docx_numbered_facts(document, "Anchored Chronology", chronology_lines)

    legal_standards = draft.get("legal_standards", [])
    if legal_standards:
        self._add_docx_section(document, "Applicable Legal Standards", legal_standards)

    document.add_heading("Claims for Relief", level=1)
    for index, claim in enumerate(draft.get("claims_for_relief", []), start=1):
        document.add_heading(f"Count {_roman(index)} - {claim.get('count_title', 'Claim')}", level=2)
        self._add_docx_subsection(document, "Legal Standard", claim.get("legal_standards", []))
        incorporated_clause = self._format_incorporated_reference_clause(
            claim.get("allegation_references", []),
            claim.get("supporting_exhibits", []),
        )
        if incorporated_clause:
            self._add_docx_subsection(document, "Incorporated Support", [incorporated_clause])
        self._add_docx_subsection(document, "Claim-Specific Support", claim.get("supporting_facts", []))
        missing = claim.get("missing_elements", [])
        if missing:
            self._add_docx_subsection(document, "Open Support Gaps", missing)
        exhibits = claim.get("supporting_exhibits", [])
        if exhibits:
            document.add_paragraph("Supporting Exhibits:")
            for exhibit in exhibits:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.add_run(f"{exhibit.get('label')}. {exhibit.get('title')}")
                if exhibit.get("link"):
                    paragraph.add_run(" ")
                    self._append_docx_hyperlink(
                        paragraph,
                        exhibit["link"],
                        "Open exhibit",
                        RELATIONSHIP_TYPE,
                        OxmlElement,
                        qn,
                        RGBColor,
                    )

    self._add_docx_subsection(document, "Requested Relief", draft.get("requested_relief", []), numbered=True)
    jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
    if jury_demand:
        self._add_docx_section(document, jury_demand.get("title") or "Jury Demand", [jury_demand.get("text")])

    document.add_heading("Supporting Exhibits", level=1)
    for exhibit in draft.get("exhibits", []):
        paragraph = document.add_paragraph(style="List Bullet")
        paragraph.add_run(f"{exhibit.get('label')}. {exhibit.get('title')}")
        if exhibit.get("summary"):
            paragraph.add_run(f" - {exhibit.get('summary')}")
        if exhibit.get("link"):
            paragraph.add_run(" ")
            self._append_docx_hyperlink(
                paragraph,
                exhibit["link"],
                "Open exhibit",
                RELATIONSHIP_TYPE,
                OxmlElement,
                qn,
                RGBColor,
            )

    affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
    if affidavit:
        self._add_docx_section(
            document,
            affidavit.get("title") or "Affidavit in Support of Complaint",
            list(_coerce_list(affidavit.get("venue_lines")))
            + [affidavit.get("intro"), affidavit.get("knowledge_graph_note")],
        )
        self._add_docx_numbered_facts(document, "Affiant States as Follows", affidavit.get("facts", []))
        supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
        if supporting_exhibits:
            document.add_heading("Affidavit Supporting Exhibits", level=2)
            for exhibit in supporting_exhibits:
                if not isinstance(exhibit, dict):
                    continue
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.add_run(f"{exhibit.get('label')}. {exhibit.get('title')}")
                if exhibit.get("link"):
                    paragraph.add_run(f" ({exhibit['link']})")
        self._add_docx_section(
            document,
            "Affidavit Execution",
            [affidavit.get("dated"), affidavit.get("signature_line"), affidavit.get("jurat"), *_coerce_list(affidavit.get("notary_block"))],
        )

    verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
    if verification:
        self._add_docx_section(
            document,
            verification.get("title") or "Verification",
            [verification.get("text"), verification.get("dated"), verification.get("signature_line")],
        )
    certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
    if certificate_of_service:
        self._add_docx_section(
            document,
            certificate_of_service.get("title") or "Certificate of Service",
            [certificate_of_service.get("text")]
            + _coerce_list(certificate_of_service.get("detail_lines"))
            + [certificate_of_service.get("dated"), certificate_of_service.get("signature_line")],
        )
    signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
    self._add_docx_section(
        document,
        "Signature Block",
        self._build_signature_section_lines(signature_block, self._resolve_draft_forum_type(draft)),
    )

    document.save(path)
def _render_pdf(self, draft: Dict[str, Any], path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CourtHeader",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=12,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontName="Times-Bold",
            fontSize=13,
            leading=15,
            textColor=colors.black,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RightAligned",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=12,
            leading=14,
            alignment=TA_RIGHT,
            spaceAfter=8,
        )
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        topMargin=inch,
        bottomMargin=inch,
        leftMargin=inch,
        rightMargin=inch,
    )
    case_caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
    caption_party_lines = case_caption.get("caption_party_lines") if isinstance(case_caption.get("caption_party_lines"), list) else self._build_caption_party_lines(case_caption)
    story = [
        Paragraph(escape(draft.get("court_header", "")), styles["CourtHeader"]),
        Paragraph(
            "<br/><br/>".join(escape(line).replace("\n", "<br/>") for line in caption_party_lines),
            styles["Caption"],
        ),
        Paragraph(
            escape(
                f"{case_caption.get('case_number_label', 'Civil Action No.')} {case_caption.get('case_number', '________________')}"
                + (
                    f"\n{case_caption.get('lead_case_number_label', 'Lead Case No.')} {case_caption.get('lead_case_number')}"
                    if case_caption.get('lead_case_number')
                    else ""
                )
                + (
                    f"\n{case_caption.get('related_case_number_label', 'Related Case No.')} {case_caption.get('related_case_number')}"
                    if case_caption.get('related_case_number')
                    else ""
                )
                + (
                    f"\n{case_caption.get('assigned_judge_label', 'Assigned Judge')}: {case_caption.get('assigned_judge')}"
                    if case_caption.get('assigned_judge')
                    else ""
                )
                + (
                    f"\n{case_caption.get('courtroom_label', 'Courtroom')}: {case_caption.get('courtroom')}"
                    if case_caption.get('courtroom')
                    else ""
                )
            ),
            styles["RightAligned"],
        ),
        Paragraph(
            escape(draft.get("case_caption", {}).get("document_title", "COMPLAINT")),
            styles["CourtHeader"],
        ),
        *(
            [
                Paragraph(
                    escape(draft["case_caption"]["jury_demand_notice"]),
                    styles["CourtHeader"],
                )
            ]
            if draft.get("case_caption", {}).get("jury_demand_notice")
            else []
        ),
        Spacer(1, 8),
    ]

    self._append_pdf_section(story, styles, "Nature of the Action", draft.get("nature_of_action", []))
    self._append_pdf_section(
        story,
        styles,
        "Parties",
        [
            f"Plaintiff: {', '.join(draft.get('parties', {}).get('plaintiffs', []))}.",
            f"Defendant: {', '.join(draft.get('parties', {}).get('defendants', []))}.",
        ],
    )
    self._append_pdf_section(
        story,
        styles,
        "Jurisdiction and Venue",
        [draft.get("jurisdiction_statement"), draft.get("venue_statement")],
    )
    self._append_pdf_numbered_section(story, styles, "Summary of Facts", draft.get("summary_of_facts", []))
    self._append_pdf_numbered_section(
        story,
        styles,
        "Factual Allegations",
        draft.get("factual_allegations") or draft.get("summary_of_facts", []),
        groups=draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else None,
    )
    self._append_pdf_numbered_section(story, styles, "Anchored Chronology", draft.get("anchored_chronology_summary", []))
    self._append_pdf_section(
        story,
        styles,
        "Applicable Legal Standards",
        draft.get("legal_standards", []),
    )

    story.append(Paragraph("Claims for Relief", styles["SectionHeading"]))
    for index, claim in enumerate(draft.get("claims_for_relief", []), start=1):
        story.append(
            Paragraph(
                escape(f"Count {_roman(index)} - {claim.get('count_title', 'Claim')}"),
                styles["Heading2"],
            )
        )
        self._append_pdf_section(story, styles, "Legal Standard", claim.get("legal_standards", []), heading_style="Heading3")
        incorporated_clause = self._format_incorporated_reference_clause(
            claim.get("allegation_references", []),
            claim.get("supporting_exhibits", []),
        )
        if incorporated_clause:
            self._append_pdf_section(story, styles, "Incorporated Support", [incorporated_clause], heading_style="Heading3")
        self._append_pdf_section(story, styles, "Claim-Specific Support", claim.get("supporting_facts", []), heading_style="Heading3")
        if claim.get("missing_elements"):
            self._append_pdf_section(story, styles, "Open Support Gaps", claim.get("missing_elements", []), heading_style="Heading3")
        if claim.get("supporting_exhibits"):
            story.append(Paragraph("Supporting Exhibits", styles["Heading3"]))
            for exhibit in claim.get("supporting_exhibits", []):
                story.append(
                    Paragraph(
                        self._pdf_exhibit_markup(exhibit),
                        styles["Normal"],
                    )
                )

    self._append_pdf_numbered_section(story, styles, "Requested Relief", draft.get("requested_relief", []))
    jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
    if jury_demand:
        self._append_pdf_section(story, styles, jury_demand.get("title") or "Jury Demand", [jury_demand.get("text")])
    story.append(Paragraph("Supporting Exhibits", styles["SectionHeading"]))
    for exhibit in draft.get("exhibits", []):
        story.append(Paragraph(self._pdf_exhibit_markup(exhibit), styles["Normal"]))

    affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
    if affidavit:
        self._append_pdf_section(
            story,
            styles,
            affidavit.get("title") or "Affidavit in Support of Complaint",
            list(_coerce_list(affidavit.get("venue_lines"))) + [affidavit.get("intro"), affidavit.get("knowledge_graph_note")],
        )
        self._append_pdf_numbered_section(story, styles, "Affiant States as Follows", affidavit.get("facts", []))
        supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
        if supporting_exhibits:
            story.append(Paragraph("Affidavit Supporting Exhibits", styles["Heading3"]))
            for exhibit in supporting_exhibits:
                if not isinstance(exhibit, dict):
                    continue
                story.append(Paragraph(self._pdf_exhibit_markup(exhibit), styles["Normal"]))
        self._append_pdf_section(
            story,
            styles,
            "Affidavit Execution",
            [affidavit.get("dated"), affidavit.get("signature_line"), affidavit.get("jurat"), *_coerce_list(affidavit.get("notary_block"))],
        )

    verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
    if verification:
        self._append_pdf_section(
            story,
            styles,
            verification.get("title") or "Verification",
            [verification.get("text"), verification.get("dated"), verification.get("signature_line")],
        )
    certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
    if certificate_of_service:
        self._append_pdf_section(
            story,
            styles,
            certificate_of_service.get("title") or "Certificate of Service",
            [certificate_of_service.get("text")]
            + _coerce_list(certificate_of_service.get("detail_lines"))
            + [certificate_of_service.get("dated"), certificate_of_service.get("signature_line")],
        )
    signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
    self._append_pdf_section(
        story,
        styles,
        "Signature Block",
        self._build_signature_section_lines(signature_block, self._resolve_draft_forum_type(draft)),
    )

    doc.build(story)
