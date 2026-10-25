"""HTTP and MCP carry the shared WorkflowActionService inquiry contract.

A real workspace transition supplies the pending inquiry id, question
revision, interview action, explanation, graph targets, and expected updates.
A stale revision or a different inquiry id is an explicit conflict and leaves
the current graph revision in place. Omitting the expected revision still
follows the service rule and may advance. Multi-chunk ASGI bodies are not
rewritten, and this module does not claim WebSocket or SSE support.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.case_routes import (
    INQUIRY_CONFLICT_STATUS,
    _inquiry_conflict_send,
    shared_inquiry_conflict,
)
from applications.complaint_mcp_protocol import tool_list_payload
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

USER_ID = "synthetic-gui-14"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns."
ANSWER = "Alex Rivera was my supervisor at Northwind Tools and fired me on March 4, 2024."
PASSPHRASE = "synthetic-gui-14-passphrase"


def _service(tmp_path: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _client(service: ComplaintWorkspaceService) -> TestClient:
    app = FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    return TestClient(app)


def _fingerprint(body: dict) -> tuple:
    interview = body.get("interview") if isinstance(body.get("interview"), dict) else {}
    graph = interview.get("graph") if isinstance(interview.get("graph"), dict) else {}
    return (
        interview.get("session_revision"),
        interview.get("expected_question_revision"),
        interview.get("answered_count"),
        graph.get("graph_version"),
        graph.get("entity_count"),
        (interview.get("inquiry") or {}).get("inquiry_id") if isinstance(interview.get("inquiry"), dict) else None,
    )


def _assert_contract(body: dict) -> dict:
    interview = body["interview"]
    inquiry = interview["inquiry"]
    assert body["pending_inquiry_id"] == inquiry["inquiry_id"]
    assert body["pending_inquiry_id"].startswith("inq-")
    assert body["inquiry"]["inquiry_id"] == inquiry["inquiry_id"]
    assert body["expected_question_revision"] == interview["expected_question_revision"]
    assert body["expected_question_revision"] == inquiry["revision"]
    assert body["interview_action"] == interview["action"]
    assert body["explanation"]["source"] == "WorkflowActionService"
    assert body["explanation"]["why_it_matters"] == inquiry.get("why_it_matters")
    assert body["explanation"]["grounding_status"] == inquiry.get("grounding_status")
    targets = body["graph_targets"]
    assert targets["objective_id"] == inquiry.get("objective_id")
    assert targets["target_id"] == inquiry.get("target_id")
    assert targets["target_revision"] == inquiry.get("target_revision")
    assert targets["graph_id"] == interview["graph"]["graph_id"]
    assert targets["graph_version"] == interview["graph"]["graph_version"]
    assert targets["session_revision"] == interview["session_revision"]
    assert targets["legal_sufficiency"] is False
    assert body["expected_updates"] == inquiry.get("expected_update_contract")
    assert body["legal_sufficiency"] is False
    return inquiry


def test_http_carries_service_inquiry_and_conflicts_do_not_advance(tmp_path: Path) -> None:
    client = _client(_service(tmp_path))
    started = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": NARRATIVE, "question_id": "original_complaint", "interview_action": "start"},
    )
    assert started.status_code == 200, started.text
    started_body = started.json()
    inquiry = _assert_contract(started_body)
    assert started_body["interview_action"] == "start"
    assert started_body["conflict"] is None
    assert started_body["interview"]["status"] == "awaiting_user"
    before = _fingerprint(started_body)

    stale = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": "This stale answer must not change the graph.",
            "question_id": inquiry["inquiry_id"],
            "expected_question_revision": int(inquiry["revision"]) + 3,
            "interview_action": "answer",
        },
    )
    assert stale.status_code == INQUIRY_CONFLICT_STATUS
    stale_body = stale.json()
    _assert_contract(stale_body)
    assert stale_body["conflict"] == "stale_question"
    assert stale_body["interview"]["status"] == "refused"
    assert stale_body["interview"]["error"]["code"] == "stale_question"
    assert stale_body["interview_action"] == "answer"
    assert _fingerprint(stale_body) == before

    mismatched = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": "This answer names a different inquiry.",
            "question_id": "inq-not-the-pending-question",
            "expected_question_revision": inquiry["revision"],
            "interview_action": "answer",
        },
    )
    assert mismatched.status_code == INQUIRY_CONFLICT_STATUS
    mismatched_body = mismatched.json()
    assert mismatched_body["conflict"] == "stale_question"
    assert mismatched_body["pending_inquiry_id"] == inquiry["inquiry_id"]
    assert _fingerprint(mismatched_body) == before

    status = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "interview_action": "status"},
    )
    assert status.status_code == 200
    status_body = status.json()
    _assert_contract(status_body)
    assert status_body["interview_action"] == "status"
    assert status_body["conflict"] is None
    assert _fingerprint(status_body) == before

    advanced = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": ANSWER,
            "question_id": inquiry["inquiry_id"],
            "interview_action": "answer",
        },
    )
    assert advanced.status_code == 200, advanced.text
    advanced_body = advanced.json()
    _assert_contract(advanced_body)
    assert advanced_body["conflict"] is None
    error = advanced_body["interview"].get("error")
    if error is not None:
        assert error["code"] == "provider_unavailable"
        assert error["resumable"] is True
    assert _fingerprint(advanced_body) != before
    assert advanced_body["interview"]["answered_count"] == started_body["interview"]["answered_count"] + 1
    assert advanced_body["interview"]["session_revision"] == started_body["interview"]["session_revision"] + 1
    client.close()


def test_mcp_schema_and_stale_call_conflict(tmp_path: Path) -> None:
    service = _service(tmp_path)
    listed = tool_list_payload(service)
    schema = next(item["inputSchema"] for item in listed["tools"] if item["name"] == "complaint.run_intake_chat_turn")
    assert "expected_question_revision" in schema["properties"]
    assert "interview_action" in schema["properties"]
    assert "question_id" in schema["properties"]

    client = _client(service)
    started = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "start-1",
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {
                    "user_id": USER_ID,
                    "message": NARRATIVE,
                    "question_id": "original_complaint",
                    "interview_action": "start",
                },
            },
        },
    )
    assert started.status_code == 200, started.text
    started_result = started.json()["result"]
    assert started_result["isError"] is False
    started_body = started_result["structuredContent"]
    inquiry = _assert_contract(started_body)
    before = _fingerprint(started_body)

    stale = client.post(
        "/api/complaint-workspace/mcp/call",
        json={
            "tool_name": "complaint.run_intake_chat_turn",
            "arguments": {
                "user_id": USER_ID,
                "message": "MCP stale answer",
                "question_id": inquiry["inquiry_id"],
                "expected_question_revision": int(inquiry["revision"]) + 9,
                "interview_action": "answer",
            },
        },
    )
    assert stale.status_code == INQUIRY_CONFLICT_STATUS
    stale_body = stale.json()
    assert stale_body["isError"] is True
    assert stale_body["conflict"] == "stale_question"
    _assert_contract(stale_body)
    assert _fingerprint(stale_body) == before

    current = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "status-1",
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {"user_id": USER_ID, "interview_action": "status"},
            },
        },
    )
    assert current.status_code == 200
    current_body = current.json()["result"]["structuredContent"]
    assert current.json()["result"]["isError"] is False
    assert _fingerprint(current_body) == before

    matched = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "answer-1",
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {
                    "user_id": USER_ID,
                    "message": ANSWER,
                    "question_id": inquiry["inquiry_id"],
                    "expected_question_revision": inquiry["revision"],
                    "interview_action": "answer",
                },
            },
        },
    )
    assert matched.status_code == 200, matched.text
    matched_result = matched.json()["result"]
    assert matched_result["isError"] is False
    assert matched_result["conflict"] is None
    matched_body = matched_result["structuredContent"]
    _assert_contract(matched_body)
    assert matched_body["interview"]["session_revision"] == started_body["interview"]["session_revision"] + 1
    assert "MCP stale answer" not in matched.text
    client.close()


def test_route_boundary_rewrites_stale_inquiry_to_conflict() -> None:
    assert shared_inquiry_conflict({"interview": {"status": "awaiting_user", "error": None}}) is False
    assert shared_inquiry_conflict({"status": "refused", "error": {"code": "stale_question"}}) is False

    payload = {
        "interview": {
            "action": "answer",
            "status": "refused",
            "inquiry": {"inquiry_id": "inq-current", "revision": 2},
            "expected_question_revision": 2,
            "error": {"code": "stale_question", "resumable": True},
        }
    }
    ok_payload = {"interview": {"action": "status", "status": "awaiting_user", "error": None}}

    def _exchange(path: str, body: dict) -> list:
        captured = []

        async def send(message):
            captured.append(message)

        wrapped = _inquiry_conflict_send(path, send)
        encoded = json.dumps(body).encode("utf-8")
        import asyncio
        asyncio.run(wrapped({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]}))
        asyncio.run(wrapped({"type": "http.response.body", "body": encoded, "more_body": False}))
        return captured

    conflict = _exchange("/api/complaint-workspace/intake-chat", payload)
    assert conflict[0]["status"] == INQUIRY_CONFLICT_STATUS
    echoed = json.loads(conflict[1]["body"])
    assert echoed["interview"]["inquiry"]["inquiry_id"] == "inq-current"
    assert shared_inquiry_conflict(echoed) is True

    unchanged = _exchange("/api/complaint-workspace/session", payload)
    assert unchanged[0]["status"] == 200

    healthy = _exchange("/api/complaint-workspace/mcp/rpc", ok_payload)
    assert healthy[0]["status"] == 200


def _asgi_stale_inquiry_bytes() -> bytes:
    return json.dumps({"interview": {"action": "answer", "status": "refused",
        "error": {"code": "stale_question", "resumable": True}}}).encode()


def _asgi_response_messages(path, status, chunks):
    """Run a real ASGI exchange with a strict response-message consumer."""
    import asyncio
    headers = [(b"content-type", b"application/json"), (b"x-synthetic", b"preserved"),
        (b"set-cookie", b"one=1"), (b"set-cookie", b"two=2"),
        (b"content-length", str(sum(len(body) for body, _more in chunks)).encode())]
    expected = [{"type": "http.response.start", "status": status, "headers": headers}]
    expected.extend({"type": "http.response.body", "body": body, "more_body": more}
        for body, more in chunks)
    observed = []

    async def app(scope, receive, send):
        wrapped = _inquiry_conflict_send(scope["path"], send)
        for message in expected:
            await wrapped(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            assert not any(item["type"] == "http.response.start" for item in observed), "duplicate ASGI response start"
        if message["type"] == "http.response.body":
            assert observed and observed[0]["type"] == "http.response.start"
        observed.append(message)

    asyncio.run(app({"type": "http", "path": path, "method": "POST"}, receive, send))
    return observed, expected


@pytest.mark.parametrize("path,status,chunks", [
    ("/api/complaint-workspace/intake-chat", 200, [(b"stream-prefix", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/mcp/rpc", 202, [(b"\x00\xff", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/intake-chat", 409, [(b"stream-prefix", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/intake-chat", 200, [(b"", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/mcp/call", 200, [(b"\x00", True), (b"\xff\xfe", True), (b"", False)]),
    ("/api/complaint-workspace/session", 200, [(b"stream-prefix", True), (_asgi_stale_inquiry_bytes(), False)]),
])
def test_asgi_stream_forwards_exactly_one_start_and_all_original_chunks(path, status, chunks):
    assert shared_inquiry_conflict(json.loads(_asgi_stale_inquiry_bytes())) is True
    observed, expected = _asgi_response_messages(path, status, chunks)
    assert observed == expected
    assert sum(message["type"] == "http.response.start" for message in observed) == 1


@pytest.mark.parametrize("path,status,body", [
    ("/api/complaint-workspace/intake-chat", 403, _asgi_stale_inquiry_bytes()),
    ("/api/complaint-workspace/mcp/rpc", 422, _asgi_stale_inquiry_bytes()),
    ("/api/complaint-workspace/session", 200, _asgi_stale_inquiry_bytes()),
    ("/api/complaint-workspace/intake-chat", 200, b"\x00\xffnot-json\xfe"),
])
def test_asgi_single_body_preserves_non_success_unrelated_and_raw_responses(path, status, body):
    observed, expected = _asgi_response_messages(path, status, [(body, False)])
    assert observed == expected
