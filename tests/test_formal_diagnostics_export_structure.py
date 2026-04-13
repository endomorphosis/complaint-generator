from applications.complaint_workspace import ComplaintWorkspaceService


def test_formal_diagnostics_include_export_structure_summary(tmp_path, monkeypatch):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "formal-diagnostics-structure")

    monkeypatch.setattr(
        service,
        "analyze_complaint_output",
        lambda user_id: {
            "user_id": user_id,
            "ui_feedback": {
                "claim_type_alignment_score": 92,
                "filing_shape_score": 88,
                "release_gate": {"verdict": "pass"},
                "formal_diagnostics": {"release_gate_verdict": "pass"},
                "router_review": {"backend": {"provider": "template"}},
            },
            "packet_summary": {
                "has_draft": True,
                "draft_strategy": "template",
                "formal_defect_count": 0,
                "high_severity_issue_count": 0,
                "complaint_output_router_backend": {"provider": "template"},
            },
        },
    )
    monkeypatch.setattr(
        service,
        "build_export_artifact",
        lambda user_id, output_format="markdown": {
            "filename": "complaint.md",
            "media_type": "text/markdown",
            "body": (
                b"IN THE CIRCUIT COURT OF THE STATE OF OREGON\n"
                b"FOR THE COUNTY OF CLACKAMAS\n\n"
                b"Case No. 26PR00641\n\n"
                b"Taylor Smith,\nPlaintiff,\n"
                b"v.\nAcme Housing Authority,\nDefendant.\n\n"
                b"COMPLAINT\n\n"
                b"## Factual Allegations\n"
                b"1. Plaintiff requested a grievance hearing.\n"
                b"2. Defendant issued a written denial notice.\n"
            ),
        },
    )

    payload = service.get_formal_diagnostics("structure-user")
    export_structure = payload["export_structure"]
    summary = export_structure["summary"]

    assert payload["claim_type_alignment_score"] == 92
    assert summary["has_header"] is True
    assert summary["court_line_count"] >= 1
    assert summary["section_count"] >= 1
    assert summary["numbered_paragraph_count"] == 2
    assert summary["title"] == "COMPLAINT"
    assert isinstance(export_structure["sections"], list)
