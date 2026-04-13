from applications.complaint_workspace import ComplaintWorkspaceService


def test_generate_complaint_sanitizes_legacy_intake_noise(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "legacy-noise-sessions")
    user_id = "legacy-noise-user"

    service.submit_intake_answers(
        user_id,
        {
            "party_name": "I am Benjamin Barber, my address is 10043 SE 32nd ave milwaukie, oregon 97222",
            "opposing_party": "Benjamin Barber, Jane Cortez, and Julio Cortez vs Housing Authority of Clackamas County and Quantum Residential",
            "protected_activity": "reported discrimination, requested disability accommodation, and filed complaints",
            "adverse_action": "received a 30-day eviction notice and lease removal/reinstatement disruptions",
            "timeline": (
                "In October 2025, I requested lease bifurcation. In November 2025, I obtained a restraining order. "
                "In January 2026, I was removed from the lease and the restrained party was restored. "
                "In February 2026, I was restored to the lease. On March 20, 2026, TPV was issued late."
            ),
            "harm": "financial losses and lost opportunities",
        },
    )
    service.update_claim_type(user_id, "housing_discrimination")

    payload = service.generate_complaint(user_id)
    draft = payload["draft"]
    body = draft["body"]

    assert "Benjamin Barber v. Housing Authority of Clackamas County and Quantum Residential" in draft["title"]
    assert "my address is 10043" not in body
    assert "Housing Authority of Clackamas County and Quantum Residential, Defendant." in body
    assert "October 2025" in body
    assert "March 20, 2026" in body
