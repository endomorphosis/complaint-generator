"""Physical UX13 boundary probe: actual ciphertext, keys, sessions and ASGI.

The sole fault injection is a bounded gate that delegates the production
ciphertext backend unchanged. It does not manufacture an HTTP response,
plaintext, key, cryptographic receipt, session, or authorizer outcome.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_message_api import CaseMessageService
from applications.case_routes import compose_case_routes
from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login
from tests.test_cimp_ux_13 import _receive, ORIGINAL, SOURCE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


class _GatedCiphertextBackend:
    """Delegate authentic ciphertext unchanged; hold only one requested read."""
    def __init__(self):
        self.actual = MemoryByteBackend()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.armed = False
        self.ciphertext_read = False

    def add(self, data, pin=True):
        return self.actual.add(data, pin=pin)

    def cat(self, cid):
        payload = self.actual.cat(cid)
        if self.armed:
            self.armed = False
            assert isinstance(payload, bytes)
            assert ORIGINAL.encode() not in payload and SOURCE.encode() not in payload
            self.ciphertext_read = True
            self.entered.set()
            if not self.release.wait(10):
                raise AssertionError("private test ciphertext gate timed out")
        return payload


def _actual_world(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = _GatedCiphertextBackend()
    workspace = EvidenceWorkspace(world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend, tmp_path / "evidence-root")
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_assignments=world.assignments, case_messages=CaseMessageService(world.messages),
        case_reviews=world.reviews, case_consent=world.consent, evidence_workspace=workspace,
        include_review=False, include_document=False)
    return world, app, backend


def test_actual_http_catalog_retires_key_locked_during_ciphertext_read(tmp_path):
    world, app, backend = _actual_world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        created = _receive(client, world.case, csrf, idempotency_key="private-probe-receive")
        assert created.status_code == 201
        assert created.json()["receipt"]["ciphertext_readback"] is True
        headers = _composed_headers(world.case, csrf)
        before = client.get("/api/cases/evidence", headers=headers)
        assert before.status_code == 200
        assert len(before.json()["items"]) == 1
        assert before.json()["items"][0]["original_filename"] == ORIGINAL
        backend.armed = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.get, "/api/cases/evidence", headers=headers)
            try:
                assert backend.entered.wait(10), "real encrypted catalog read did not reach gate"
                assert backend.ciphertext_read is True
                assert not pending.done()
                state = world.owner_keys.lock()
                assert state["unlocked"] is False
                assert world.owner_keys.unlocked is False
            finally:
                backend.release.set()
            response = pending.result(timeout=10)
        body = response.json()
        rows = body.get("items", [])
        observed = {"http_status": response.status_code,
            "key_unlocked_after_lock": world.owner_keys.unlocked,
            "catalog_item_count": len(rows),
            "private_filename_visible": any(row.get("original_filename") == ORIGINAL for row in rows),
            "actual_ciphertext_read": backend.ciphertext_read,
            "completion_authority": False}
        (tmp_path / "closed_observation.json").write_text(json.dumps(observed, sort_keys=True))
        # A new request is genuinely refused by the same actual owner service.
        following = client.get("/api/cases/evidence", headers=headers)
        assert following.status_code == 503
        assert following.json()["items"] == []
        assert response.status_code == 503, observed
        assert rows == [], observed
        assert body.get("ingestion_status") == "unavailable", observed
