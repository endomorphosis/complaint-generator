from __future__ import annotations

import pytest


pytestmark = [pytest.mark.no_auto_network]


def test_p2p_task_queue_provider_submits_waits_and_extracts_text(monkeypatch, tmp_path):
    from ipfs_datasets_py import llm_router

    monkeypatch.setenv("IPFS_DATASETS_PY_ROUTER_RESPONSE_CACHE", "0")
    calls = {}

    def fake_submit_task(**kwargs):
        calls["submit"] = kwargs
        return "task-123"

    def fake_wait_task(task_id, **kwargs):
        calls["wait"] = {"task_id": task_id, **kwargs}
        return {"status": "completed", "result": {"text": "remote text"}}

    monkeypatch.setattr(llm_router, "submit_task", fake_submit_task)
    monkeypatch.setattr(llm_router, "wait_task", fake_wait_task)

    result = llm_router.generate_text(
        "hello remote",
        provider="p2p_task_queue",
        model_name="gpt2",
        queue_path=str(tmp_path / "queue.duckdb"),
        wait_timeout_s=12,
        max_tokens=7,
        temperature=0.4,
    )

    assert result == "remote text"
    assert calls["submit"]["prompt"] == "hello remote"
    assert calls["submit"]["model_name"] == "gpt2"
    assert calls["submit"]["task_type"] == "text-generation"
    assert calls["submit"]["queue_path"].endswith("queue.duckdb")
    assert calls["submit"]["max_tokens"] == 7
    assert calls["submit"]["temperature"] == 0.4
    assert calls["wait"]["task_id"] == "task-123"
    assert calls["wait"]["timeout_s"] == 12.0


def test_p2p_task_queue_provider_reports_failed_task(monkeypatch):
    from ipfs_datasets_py import llm_router

    monkeypatch.setenv("IPFS_DATASETS_PY_ROUTER_RESPONSE_CACHE", "0")
    monkeypatch.setattr(llm_router, "submit_task", lambda **kwargs: "task-123")
    monkeypatch.setattr(
        llm_router,
        "wait_task",
        lambda task_id, **kwargs: {"status": "failed", "error": "no worker available"},
    )

    with pytest.raises(llm_router.LLMRouterError, match="no worker available"):
        llm_router.generate_text("hello remote", provider="p2p_task_queue")


def test_multimodal_router_sends_real_image_payloads_to_p2p_task_queue(monkeypatch, tmp_path):
    from ipfs_datasets_py import llm_router, multimodal_router

    monkeypatch.setenv("IPFS_DATASETS_PY_ROUTER_RESPONSE_CACHE", "0")
    calls = {}
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"fake png bytes")

    def fake_submit_task(**kwargs):
        calls["submit"] = kwargs
        return "task-456"

    def fake_wait_task(task_id, **kwargs):
        calls["wait"] = {"task_id": task_id, **kwargs}
        return {"status": "completed", "result": {"text": "remote multimodal fallback"}}

    monkeypatch.setattr(llm_router, "submit_task", fake_submit_task)
    monkeypatch.setattr(llm_router, "wait_task", fake_wait_task)

    result = multimodal_router.generate_multimodal_text(
        "review screen",
        provider="p2p_task_queue",
        model_name="gpt2",
        image_paths=[image_path],
        image_urls=["https://example.test/screen.png"],
        remote_provider="openai",
        temperature=0.1,
    )

    assert result == "remote multimodal fallback"
    assert calls["submit"]["prompt"] == "review screen"
    assert calls["submit"]["task_type"] == "multimodal-generation"
    payload = calls["submit"]["payload"]
    assert payload["prompt"] == "review screen"
    assert payload["provider"] == "openai"
    assert payload["temperature"] == 0.1
    assert payload["image_urls"] == ["https://example.test/screen.png"]
    assert len(payload["image_data_urls"]) == 1
    assert payload["image_data_urls"][0].startswith("data:image/png;base64,")


def test_multimodal_worker_reconstructs_remote_image_payload(monkeypatch):
    from ipfs_accelerate_py.p2p_tasks import worker

    monkeypatch.setenv("IPFS_ACCELERATE_PY_TASK_WORKER_ALLOWED_MULTIMODAL_PROVIDERS", "openai")
    captured = {}

    def fake_generate_multimodal_text(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "worker vision ok"

    import ipfs_datasets_py.multimodal_router as multimodal_router

    monkeypatch.setattr(multimodal_router, "generate_multimodal_text", fake_generate_multimodal_text)

    result = worker._run_multimodal_generation(
        {
            "task_id": "task-1",
            "task_type": "multimodal-generation",
            "model_name": "vision-model",
            "assigned_worker": "worker-a",
            "payload": {
                "prompt": "inspect image",
                "provider": "openai",
                "image_urls": ["https://example.test/screen.png"],
                "image_data_urls": ["data:image/png;base64,ZmFrZQ=="],
                "system_prompt": "be precise",
                "additional_text_blocks": ["one", "two"],
                "temperature": 0.2,
            },
        }
    )

    assert result["text"] == "worker vision ok"
    assert captured["args"] == ("inspect image",)
    assert captured["kwargs"]["provider"] == "openai"
    assert captured["kwargs"]["model_name"] == "vision-model"
    assert captured["kwargs"]["image_urls"] == [
        "https://example.test/screen.png",
        "data:image/png;base64,ZmFrZQ==",
    ]
    assert captured["kwargs"]["system_prompt"] == "be precise"
    assert captured["kwargs"]["additional_text_blocks"] == ["one", "two"]
    assert captured["kwargs"]["temperature"] == 0.2
