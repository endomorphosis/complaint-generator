"""Tenant and case isolation for private complaint workspaces.

Synthetic principals only. No live model, network, keyring, daemon, or real complaint files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_mcp_protocol import handle_jsonrpc_message
from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    PrincipalRegistry,
    WorkspaceAccess,
    WorkspaceAuthorizationDenied,
    WorkspaceAuthorizer,
    _slugify_user_id,
    principal_namespace,
)
from applications.complaint_workspace_api import create_complaint_workspace_router
from complaint_generator.workspace import set_privacy_policy, start_session

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ALICE = "alice/bob"
BOB = "alice bob"
MARKER = "SYNTHETIC_PRIVATE_MARKER_cimp_priv_002"
OTHER_MARKER = "SYNTHETIC_OTHER_MARKER_cimp_priv_002"


class _DenyAll(WorkspaceAuthorizer):
    def __call__(self, requirement, context) -> bool:
        return False


def _service(root: Path, access: WorkspaceAccess, authorizer=None) -> ComplaintWorkspaceService:
    return ComplaintWorkspaceService(root_dir=root, access=access, authorizer=authorizer)


def _plant_legacy(service: ComplaintWorkspaceService, owner: str, marker: str) -> Path:
    path = service._legacy_session_path(owner)
    path.write_text(
        json.dumps(
            {
                "user_id": owner,
                "case_id": owner,
                "intake_answers": {"party_name": marker},
            }
        ),
        encoding="utf-8",
    )
    return path


def _registry() -> PrincipalRegistry:
    registry = PrincipalRegistry()
    registry.register("token-alice", ALICE, case_id=ALICE)
    registry.register("token-bob", BOB, case_id=BOB)
    return registry


def _client(service: ComplaintWorkspaceService, registry: PrincipalRegistry | None = None, *, trusted_local: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_complaint_workspace_router(
            service,
            principal_registry=registry,
            trusted_local=trusted_local,
        )
    )
    return TestClient(app)


def test_colliding_legacy_slugs_do_not_share_namespace_or_data(tmp_path: Path) -> None:
    assert _slugify_user_id(ALICE) == _slugify_user_id(BOB)
    assert principal_namespace(ALICE) != principal_namespace(BOB)

    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    bob = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    legacy = _plant_legacy(alice, ALICE, MARKER)
    legacy_bytes = legacy.read_bytes()

    alice_session = alice.get_session(ALICE)
    bob_session = bob.get_session(BOB)

    assert alice_session["session"]["intake_answers"]["party_name"] == MARKER
    assert bob_session["session"]["intake_answers"] == {}
    assert MARKER not in json.dumps(bob_session)
    assert alice._session_path(ALICE) != bob._session_path(BOB)
    assert alice._session_path(ALICE).is_file()
    assert bob._session_path(BOB).is_file()
    assert legacy.read_bytes() == legacy_bytes
    mapping = json.loads((root / "legacy-namespace-map.json").read_text(encoding="utf-8"))
    legacy_name = alice._legacy_filename(ALICE)
    assert legacy_name == f"{_slugify_user_id(ALICE)}.json"
    assert mapping["entries"][legacy_name]["owner"] == ALICE
    assert mapping["entries"][legacy_name]["namespace"] == principal_namespace(ALICE)

    alice.set_privacy_policy(ALICE, "grok")
    bob.set_privacy_policy(BOB, "local")
    assert alice.get_privacy_policy(ALICE)["policy"]["processing_mode"] != bob.get_privacy_policy(BOB)["policy"]["processing_mode"]
    assert bob.get_privacy_policy(BOB)["at_rest_protection"] == "plaintext_pending"
    assert MARKER not in json.dumps(bob.get_privacy_policy(BOB))


def test_legacy_owner_mismatch_is_not_deserialized_or_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    legacy = _plant_legacy(alice, "someone-else", MARKER)
    before = legacy.read_bytes()
    opened = alice.get_session(ALICE)
    assert opened["session"]["intake_answers"] == {}
    assert MARKER not in json.dumps(opened)
    assert legacy.read_bytes() == before
    assert not (root / "legacy-namespace-map.json").exists()


def test_unauthenticated_and_foreign_principals_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    owner = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    owner.submit_intake_answers(ALICE, {"party_name": MARKER})
    anonymous = _service(root, WorkspaceAccess.unauthenticated())
    foreign = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    denied_authorizer = _service(root, WorkspaceAccess.trusted_local(), authorizer=_DenyAll())

    for actor, requested in (
        (anonymous, ALICE),
        (foreign, ALICE),
        (denied_authorizer, ALICE),
    ):
        with pytest.raises(WorkspaceAuthorizationDenied) as caught:
            actor.get_session(requested)
        assert str(caught.value) == "authorization_denied"
        assert MARKER not in str(caught.value)

    copied = json.loads(owner._session_path(ALICE).read_text(encoding="utf-8"))
    copied["user_id"] = BOB
    copied["intake_answers"] = {"party_name": OTHER_MARKER}
    owner._session_path(ALICE).write_text(json.dumps(copied), encoding="utf-8")
    with pytest.raises(WorkspaceAuthorizationDenied) as wrong_owner:
        owner.get_session(ALICE)
    assert MARKER not in str(wrong_owner.value)
    assert OTHER_MARKER not in str(wrong_owner.value)


def test_wrong_case_and_reference_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    alice.submit_intake_answers(ALICE, {"party_name": MARKER})
    alice.remember_private_reference(ALICE, cid="cid-owned", storage_key="key-owned", case_id=ALICE)
    admitted = alice.resolve_private_reference(ALICE, case_id=ALICE, cid="cid-owned", storage_key="key-owned")
    assert admitted["admitted"] is True
    assert admitted["at_rest_protection"] == "plaintext_pending"
    assert MARKER not in json.dumps(admitted)

    with pytest.raises(WorkspaceAuthorizationDenied) as wrong_case:
        alice.get_session(ALICE, case_id="other-case")
    assert MARKER not in str(wrong_case.value)

    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.resolve_private_reference(ALICE, case_id=ALICE, cid="cid-foreign")
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.resolve_private_reference(ALICE, case_id="other-case", storage_key="key-owned")

    soft = alice.get_privacy_policy(ALICE, case_id="other-case")
    assert soft["load"]["admitted"] is False
    assert soft["at_rest_protection"] == "plaintext_pending"
    assert MARKER not in json.dumps(soft)

    bob = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    with pytest.raises(WorkspaceAuthorizationDenied):
        bob.resolve_private_reference(ALICE, case_id=ALICE, cid="cid-owned", storage_key="key-owned")


def test_traversal_and_symlink_escape_do_not_read_or_write(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text(MARKER, encoding="utf-8")
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    namespace = alice._session_path(ALICE)
    if namespace.exists() or namespace.is_symlink():
        namespace.unlink()
    namespace.symlink_to(secret)

    with pytest.raises(WorkspaceAuthorizationDenied) as symlink_read:
        alice.get_session(ALICE)
    assert MARKER not in str(symlink_read.value)
    assert secret.read_text(encoding="utf-8") == MARKER

    escape = root / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.read_contained_workspace_file(ALICE, "escape/secret.txt")
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.write_contained_workspace_file(ALICE, "../outside/secret.txt", b"overwritten")
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.write_contained_workspace_file(ALICE, "escape/secret.txt", b"overwritten")
    assert secret.read_text(encoding="utf-8") == MARKER

    written = alice.write_contained_workspace_file(ALICE, "note.txt", b"owned-note")
    assert written["at_rest_protection"] == "plaintext_pending"
    assert alice.read_contained_workspace_file(ALICE, "note.txt") == b"owned-note"


def test_http_mcp_and_facade_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "sessions"
    service = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    service.submit_intake_answers(ALICE, {"party_name": MARKER})
    registry = _registry()
    client = _client(service, registry)

    denied = client.get("/api/complaint-workspace/session", params={"user_id": ALICE})
    assert denied.status_code == 403
    assert MARKER not in denied.text

    forged = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": BOB},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert forged.status_code == 403
    assert MARKER not in forged.text

    allowed = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": ALICE},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["session"]["intake_answers"]["party_name"] == MARKER
    assert allowed.json()["session"]["user_id"] == ALICE

    wrong_case = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": ALICE, "case_id": "other-case"},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert wrong_case.status_code == 403
    assert MARKER not in wrong_case.text

    export_denied = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": BOB, "output_format": "json"},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert export_denied.status_code == 403
    assert MARKER not in export_denied.text

    export_ok = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": ALICE, "output_format": "json"},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert export_ok.status_code == 200
    assert MARKER in export_ok.text

    monkeypatch.setenv("COMPLAINT_MCP_AUTH_TOKEN", "generic-token")
    generic_call = client.post(
        "/api/complaint-workspace/mcp/call",
        json={"tool_name": "complaint.start_session", "arguments": {"user_id": ALICE}},
        headers={"Authorization": "Bearer generic-token"},
    )
    assert generic_call.status_code == 200
    assert generic_call.json()["isError"] is True
    assert generic_call.json()["error"] == "authorization_denied"
    assert MARKER not in generic_call.text

    generic_rpc = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "complaint.start_session", "arguments": {"user_id": ALICE, "case_id": ALICE}},
        },
        headers={"Authorization": "Bearer generic-token"},
    )
    assert generic_rpc.status_code == 200
    assert generic_rpc.json()["result"]["isError"] is True
    assert MARKER not in generic_rpc.text

    monkeypatch.delenv("COMPLAINT_MCP_AUTH_TOKEN", raising=False)
    owned_call = client.post(
        "/api/complaint-workspace/mcp/call",
        json={"tool_name": "complaint.start_session", "arguments": {"user_id": ALICE, "case_id": ALICE}},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert owned_call.status_code == 200
    assert owned_call.json()["session"]["intake_answers"]["party_name"] == MARKER

    owned_rpc = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "complaint.resolve_private_reference",
                "arguments": {"user_id": BOB, "cid": "cid-owned"},
            },
        },
        headers={"Authorization": "Bearer token-alice"},
    )
    assert owned_rpc.status_code == 200
    assert owned_rpc.json()["result"]["isError"] is True
    assert MARKER not in owned_rpc.text

    direct = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "complaint.start_session", "arguments": {"user_id": ALICE}},
        },
        access=WorkspaceAccess.unauthenticated(),
    )
    assert direct["result"]["isError"] is True
    assert MARKER not in json.dumps(direct)

    local_client = _client(ComplaintWorkspaceService(root_dir=root), trusted_local=True)
    local_session = local_client.get("/api/complaint-workspace/session", params={"user_id": "local-operator"})
    assert local_session.status_code == 200
    assert local_session.json()["session"]["user_id"] == "local-operator"
    assert MARKER not in local_session.text

    facade_root = tmp_path / "facade"
    first = start_session(ALICE, root_dir=facade_root)
    set_privacy_policy(ALICE, "local", root_dir=facade_root)
    second = start_session(BOB, root_dir=facade_root)
    assert first["session"]["user_id"] == ALICE
    assert second["session"]["user_id"] == BOB
    assert principal_namespace(first["session"]["user_id"]) != principal_namespace(second["session"]["user_id"])
    assert MARKER not in json.dumps(second)
    listed = local_client.get("/api/complaint-workspace/mcp/tools")
    assert listed.status_code == 200
