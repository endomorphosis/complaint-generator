import json
import socket
import time

import pytest


def _get_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_p2p_call_tool_end_to_end(tmp_path, monkeypatch):
    """Start the embedded libp2p service and call an MCP tool over P2P."""

    from ipfs_datasets_py.mcp_server.configs import Configs
    from ipfs_datasets_py.mcp_server.p2p_mcp_registry_adapter import P2PMCPRegistryAdapter
    from ipfs_datasets_py.mcp_server.server import IPFSDatasetsMCPServer
    from ipfs_datasets_py.mcp_server.tools.auth_tools.auth_tools import _mock_auth_service

    from ipfs_accelerate_py.p2p_tasks.client import RemoteQueue, call_tool_sync
    from ipfs_datasets_py.mcp_server.tools.p2p_tools.p2p_tools import p2p_remote_call_tool

    # Create an auth token that the host MCP server can validate.
    auth = await _mock_auth_service.authenticate("admin", "admin123")
    token = auth.get("access_token")
    assert isinstance(token, str) and token

    # The p2p client automatically injects message['token'] from this env var.
    monkeypatch.setenv("IPFS_ACCELERATE_PY_TASK_P2P_TOKEN", token)

    # Ensure announce file is written to a predictable place for discovery.
    announce_file = tmp_path / "task_p2p_announce.json"
    monkeypatch.setenv("IPFS_ACCELERATE_PY_TASK_P2P_ANNOUNCE_FILE", str(announce_file))

    listen_port = _get_free_tcp_port()

    server = IPFSDatasetsMCPServer(
        Configs(
            p2p_enabled=True,
            p2p_listen_port=listen_port,
            p2p_auth_mode="mcp_token",
            p2p_startup_timeout_s=5.0,
        )
    )

    assert server.p2p is not None

    await server.register_tools()

    adapter = P2PMCPRegistryAdapter(server)
    assert "tools_list_categories" in adapter.tools

    try:
        assert server.p2p.start(accelerate_instance=adapter) is True

        # Wait for announce file to show up.
        deadline = time.time() + 10.0
        while time.time() < deadline and not announce_file.exists():
            await __import__("anyio").sleep(0.05)

        assert announce_file.exists(), "P2P announce file was not written"

        data = json.loads(announce_file.read_text("utf-8"))
        peer_id = str(data.get("peer_id") or "").strip()
        multiaddr = str(data.get("multiaddr") or "").strip()
        assert peer_id and multiaddr

        remote = RemoteQueue(peer_id=peer_id, multiaddr=multiaddr)

        resp = call_tool_sync(remote=remote, tool_name="tools_list_categories", args={"include_count": False})
        assert isinstance(resp, dict)
        assert resp.get("ok") is True, resp
        # Contract: tools_list_categories returns {ok, categories}
        assert "categories" in resp.get("result", {}), resp

        # Also validate the mcp_server-side remote wrapper (async) works.
        resp2 = await p2p_remote_call_tool(
            tool_name="tools_list_categories",
            args={"include_count": False},
            remote_multiaddr=multiaddr,
            remote_peer_id=peer_id,
            timeout_s=20.0,
        )
        assert isinstance(resp2, dict)
        assert resp2.get("ok") is True, resp2
        assert "categories" in resp2.get("result", {}), resp2

        # Validate the workflow scheduler tools are reachable over P2P.
        init = await p2p_remote_call_tool(
            tool_name="p2p_scheduler_init",
            args={"peer_id": "peerA", "bootstrap_peers": [], "force": True},
            remote_multiaddr=multiaddr,
            remote_peer_id=peer_id,
            timeout_s=20.0,
        )
        assert init.get("ok") is True, init

        submit = await p2p_remote_call_tool(
            tool_name="p2p_scheduler_submit_task",
            args={
                "task_id": "t1",
                "workflow_id": "w1",
                "name": "do thing",
                "tags": ["p2p-only"],
                "priority": 9,
            },
            remote_multiaddr=multiaddr,
            remote_peer_id=peer_id,
            timeout_s=20.0,
        )
        assert submit.get("ok") is True, submit
        assert submit.get("result", {}).get("task", {}).get("task_id") == "t1", submit

        nxt = await p2p_remote_call_tool(
            tool_name="p2p_scheduler_get_next_task",
            args={},
            remote_multiaddr=multiaddr,
            remote_peer_id=peer_id,
            timeout_s=20.0,
        )
        assert nxt.get("ok") is True, nxt
        task = nxt.get("result", {}).get("task")
        assert isinstance(task, dict) and task.get("task_id") == "t1", nxt
        assert task.get("assigned_peer") == "peerA", nxt

        done = await p2p_remote_call_tool(
            tool_name="p2p_scheduler_mark_complete",
            args={"task_id": "t1"},
            remote_multiaddr=multiaddr,
            remote_peer_id=peer_id,
            timeout_s=20.0,
        )
        assert done.get("ok") is True, done
        assert done.get("result", {}).get("completed") is True, done
    finally:
        server.p2p.stop()
