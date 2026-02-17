from __future__ import annotations


def test_workflow_scheduler_tool_lifecycle():
    from ipfs_datasets_py.mcp_server.tools.p2p_tools import workflow_scheduler_tools as tools

    tools._reset_scheduler_for_test()

    status = tools.p2p_scheduler_status()
    assert status["ok"] is False

    init = tools.p2p_scheduler_init(peer_id="peerA")
    assert init["ok"] is True
    assert init["status"]["peer_id"] == "peerA"

    submit = tools.p2p_scheduler_submit_task(
        task_id="t1",
        workflow_id="w1",
        name="do thing",
        tags=["p2p-only"],
        priority=9,
    )
    assert submit["ok"] is True
    assert submit["task"]["task_id"] == "t1"

    nxt = tools.p2p_scheduler_get_next_task()
    assert nxt["ok"] is True
    assert nxt["task"] is not None
    assert nxt["task"]["task_id"] == "t1"
    assert nxt["task"]["assigned_peer"] == "peerA"

    done = tools.p2p_scheduler_mark_complete("t1")
    assert done["ok"] is True
    assert done["completed"] is True

    status2 = tools.p2p_scheduler_status()
    assert status2["ok"] is True
    assert status2["status"]["completed_tasks"] == 1
