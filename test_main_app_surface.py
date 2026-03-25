from fastapi.testclient import TestClient

from main import app


def test_main_app_exposes_unified_complaint_surface_routes():
    client = TestClient(app)

    landing = client.get("/")
    assert landing.status_code == 200
    assert "Lex Publicus Complaint Generator" in landing.text

    workspace = client.get("/workspace")
    assert workspace.status_code == 200
    assert "Unified Complaint Workspace" in workspace.text

    review = client.get("/claim-support-review")
    assert review.status_code == 200
    assert "Operator Review Surface" in review.text

    builder = client.get("/document")
    assert builder.status_code == 200
    assert "Formal Complaint Builder" in builder.text

    session = client.get("/api/complaint-workspace/session")
    assert session.status_code == 200
    payload = session.json()
    assert payload["session"]["user_id"]
    assert "review" in payload
