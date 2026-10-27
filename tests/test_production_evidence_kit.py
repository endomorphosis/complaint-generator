"""Production factories preserve the existing authorized evidence owner."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_ux_14 import _upload, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
FACTORIES = ("server", "review-api", "review-surface", "review-dashboard")


def _factory(name, world, evidence):
    from applications.server import SERVER
    from applications.review_api import create_review_api_app
    from applications.review_ui import create_review_surface_app, create_review_dashboard_app
    options = dict(authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=world.app.state.case_handlers, case_catalog=world.app.state.case_catalog,
        case_consent=world.consent, case_reviews=world.reviews, evidence_workspace=evidence)
    if name == "server":
        return SERVER(world.service, workspace_service=world.service, **options).app
    if name == "review-api":
        return create_review_api_app(world.service, workspace_service=world.service, **options)
    if name == "review-surface":
        return create_review_surface_app(world.service, workspace_service=world.service, **options)
    if name == "review-dashboard":
        return create_review_dashboard_app(**options)
    raise AssertionError("unknown actual production factory")


@pytest.mark.parametrize("factory", FACTORIES)
def test_production_factory_forwards_the_explicit_existing_owner(tmp_path, factory):
    world = owner_lawyer_journey_world(tmp_path / "world")
    # Explicit inherited memory owner tests only the factory compatibility seam.
    # It is neither an automatic fallback nor durability qualification.
    evidence = EvidenceWorkspace(world.cases, {world.owner.principal_id: world.owner_keys},
        MemoryByteBackend(), tmp_path / "catalog")
    app = _factory(factory, world, evidence)
    assert app.state.evidence_workspace is evidence
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/cases/evidence", headers=_composed_headers(world.case)).status_code == 401
        csrf = _composed_login(client)
        _, _, uploaded = _upload(client, world.case, csrf)
        catalog = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert catalog.status_code == 200, catalog.text
        assert [item["evidence_id"] for item in catalog.json()["items"]] == [uploaded["evidence_id"]]
