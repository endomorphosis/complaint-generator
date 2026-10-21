"""Offline trace of the terminal Grok 4.7 llm_router selection."""

import json
from pathlib import Path

import pytest

from backends.llm_router_backend import (
    PINNED_GROK_MODEL,
    PINNED_GROK_PROVIDER,
    ProviderRouteError,
    SUPPORTED_GROK_47_IDENTITIES,
    LLMRouterBackend,
    router_session_diagnostics_payload,
    router_task_receipt_payload,
)
from integrations.ipfs_accelerate.routers import INFERENCE_OWNER, PINNED_GROK_CANARY_PROMPT


ROOT = Path(__file__).resolve().parents[1]
COMPLAINT_MARKER = "COMPLAINT_PRIVATE_FACT_SHOULD_NOT_LEAK"


def _trace(provider=PINNED_GROK_PROVIDER, model=PINNED_GROK_MODEL):
    return {"effective_provider_name": provider, "effective_model_name": model}


def _backend(**overrides):
    progress = []
    config = {
        "id": "llm-router-grok-4.7",
        "provider": PINNED_GROK_PROVIDER,
        "model": PINNED_GROK_MODEL,
        "timeout_seconds": 2,
        "retry_max_attempts": 2,
        "retry_backoff_base_s": 0,
        "retry_backoff_max_s": 0,
        "retry_jitter_s": 0,
        "forbid_model_substitution": True,
        "progress_callback": progress.append,
    }
    config.update(overrides)
    backend_id = config.pop("id")
    provider = config.pop("provider")
    model = config.pop("model")
    backend = LLMRouterBackend(backend_id, provider=provider, model=model, **config)
    return backend, progress


def test_offline_fake_router_traverses_llm_router(monkeypatch):
    calls = []

    def fake_generate_text(**kwargs):
        calls.append(kwargs)
        assert kwargs["provider"] == PINNED_GROK_PROVIDER
        assert kwargs["model_name"] == PINNED_GROK_MODEL
        assert kwargs["allow_local_fallback"] is False
        assert kwargs["allow_cross_provider_fallback"] is False
        return "synthetic-ok"

    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", fake_generate_text)
    monkeypatch.setattr("integrations.ipfs_datasets.llm.get_last_generation_trace", lambda: _trace())
    backend, progress = _backend()
    session_id = backend.session_id
    text = backend("synthetic-router-probe")
    assert text == "synthetic-ok"
    assert calls, "request did not traverse llm_router generate_text"
    diagnostics = backend.sanitized_session_diagnostics()
    receipt = backend.task_receipts[-1]
    assert diagnostics["requested_router"] == INFERENCE_OWNER
    assert diagnostics["selected_router"] == INFERENCE_OWNER
    assert diagnostics["requested_provider"] == PINNED_GROK_PROVIDER
    assert diagnostics["selected_provider"] == PINNED_GROK_PROVIDER
    assert diagnostics["requested_model"] == PINNED_GROK_MODEL
    assert diagnostics["selected_model"] in SUPPORTED_GROK_47_IDENTITIES
    assert diagnostics["provider_supported_identity"] is True
    assert diagnostics["route_observation"] == "verified"
    assert receipt["requested_provider"] == PINNED_GROK_PROVIDER
    assert receipt["selected_model"] == PINNED_GROK_MODEL
    assert diagnostics["session_id"] == session_id
    assert diagnostics["session_retained"] is True
    assert diagnostics["prompt_logged"] is False
    blob = json.dumps({"diagnostics": diagnostics, "receipt": receipt, "progress": progress})
    assert "synthetic-router-probe" not in blob
    assert progress and progress[0]["phase"] == "provider_wait"


def test_unavailable_grok_does_not_substitute_codex(monkeypatch):
    def fake_generate_text(**kwargs):
        raise RuntimeError("grok binary missing")

    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", fake_generate_text)
    backend, _progress = _backend(retry_max_attempts=1)
    session_id = backend.session_id
    with pytest.raises(ProviderRouteError) as caught:
        backend(COMPLAINT_MARKER)
    payload = caught.value.payload
    assert payload["error_code"] == "provider_unavailable"
    assert payload["session_id"] == session_id
    assert payload["session_retained"] is True
    assert payload["selected_provider"] != "codex"
    assert "codex" not in payload["selected_model"]
    assert COMPLAINT_MARKER not in str(caught.value)
    assert backend.session_id == session_id
    assert backend.sanitized_session_diagnostics()["session_retained"] is True


def test_observed_codex_selection_is_refused(monkeypatch):
    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.generate_text",
        lambda **kwargs: "should-not-return",
    )
    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.get_last_generation_trace",
        lambda: _trace("codex_cli", "gpt-5.3-codex"),
    )
    backend, _progress = _backend(retry_max_attempts=1)
    session_id = backend.session_id
    with pytest.raises(ProviderRouteError) as caught:
        backend("synthetic")
    assert caught.value.payload["error_code"] == "substitution_refused"
    assert caught.value.payload["selected_provider"] == "codex_cli"
    assert backend.session_id == session_id
    assert backend.session_retained is True


def test_timeout_retry_and_cancel(monkeypatch):
    attempts = {"count": 0}

    def flaky(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("timed out talking to provider")
        return "second"

    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", flaky)
    monkeypatch.setattr("integrations.ipfs_datasets.llm.get_last_generation_trace", lambda: _trace())
    backend, progress = _backend()
    assert backend("synthetic") == "second"
    assert attempts["count"] == 2
    assert any(event["phase"] == "retry_backoff" for event in progress)

    def slow(**kwargs):
        import time
        time.sleep(5)
        return "late"

    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", slow)
    timed, _progress = _backend(timeout_seconds=0.2, retry_max_attempts=1)
    with pytest.raises(ProviderRouteError) as caught:
        timed("synthetic")
    assert caught.value.payload["error_code"] == "timeout"
    assert timed.session_retained is True

    cancelled, _progress = _backend()
    cancelled.cancel()
    with pytest.raises(ProviderRouteError) as caught:
        cancelled("synthetic")
    assert caught.value.payload["error_code"] == "cancelled"
    assert cancelled.session_retained is True


def test_structured_output_validation(monkeypatch):
    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", lambda **kwargs: "not-json")
    monkeypatch.setattr("integrations.ipfs_datasets.llm.get_last_generation_trace", lambda: _trace())
    backend, _progress = _backend(structured_output=True, response_schema={"required": ["answer"]})
    with pytest.raises(ProviderRouteError) as caught:
        backend("synthetic")
    assert caught.value.payload["error_code"] == "malformed_output"
    assert backend.session_retained is True


def test_build_label_is_provider_supported_identity(monkeypatch):
    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text", lambda **kwargs: "ok")
    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.get_last_generation_trace",
        lambda: _trace(PINNED_GROK_PROVIDER, "grok-4.7-build"),
    )
    backend, _progress = _backend()
    assert backend("synthetic") == "ok"
    receipt = backend.task_receipts[-1]
    assert receipt["selected_model"] == "grok-4.7-build"
    assert receipt["requested_model"] == PINNED_GROK_MODEL
    assert receipt["provider_supported_identity"] is True
    assert receipt["route_observation"] == "verified"


def test_config_and_launcher_select_grok47_router():
    config = json.loads((ROOT / "config.llm_router.json").read_text(encoding="utf-8"))
    backend = next(item for item in config["BACKENDS"] if item["id"] == "llm-router-grok-4.7")
    assert backend["type"] == "llm_router"
    assert backend["provider"] == PINNED_GROK_PROVIDER
    assert backend["model"] == PINNED_GROK_MODEL
    assert backend["allow_local_fallback"] is False
    assert backend["allow_cross_provider_fallback"] is False
    script = (ROOT / "scripts/run_cli_mediator.sh").read_text(encoding="utf-8")
    assert 'COMPLAINT_GENERATOR_MEDIATOR_BACKENDS="llm-router-grok-4.7"' in script
    assert "llm-router-codex" not in script.split("COMPLAINT_GENERATOR_MEDIATOR_BACKENDS", 1)[1].split("\n", 1)[0]


def test_cli_diagnostics_and_receipts_are_sanitized():
    diagnostics = router_session_diagnostics_payload(str(ROOT / "config.llm_router.json"))
    receipts = router_task_receipt_payload(str(ROOT / "config.llm_router.json"))
    assert diagnostics["requested_router"] == INFERENCE_OWNER
    assert diagnostics["requested_provider"] == PINNED_GROK_PROVIDER
    assert diagnostics["requested_model"] == PINNED_GROK_MODEL
    assert "selected_provider" in diagnostics and "selected_model" in diagnostics
    assert diagnostics["prompt_logged"] is False
    disclosure = diagnostics["remote_inference"]
    assert disclosure["sends_complaint_text_remotely"] is True
    assert disclosure["encryption_at_rest_implies_private_remote_inference"] is False
    assert "encryption at rest" in disclosure["explanation"].lower()
    assert receipts["receipts"]
    assert receipts["receipts"][0]["requested_model"] == PINNED_GROK_MODEL
    assert receipts["session_retained"] is True


def test_synthetic_live_canary_records_model_without_complaint_data():
    backend, progress = _backend()

    def transport(**kwargs):
        assert kwargs["prompt"] == PINNED_GROK_CANARY_PROMPT
        assert COMPLAINT_MARKER not in kwargs["prompt"]
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "selected_provider_name": PINNED_GROK_PROVIDER,
            "selected_model_name": "grok-4.7-build",
        }

    receipt = backend.run_synthetic_live_canary(transport=transport)
    assert receipt["canary_identity"] == "synthetic-live-canary"
    assert receipt["selected_provider"] == PINNED_GROK_PROVIDER
    assert receipt["selected_model"] == "grok-4.7-build"
    assert receipt["complaint_data_included"] is False
    assert receipt["live_canary"] is False
    assert receipt["evidence_class"] == "synthetic_canary"
    blob = json.dumps(receipt)
    assert COMPLAINT_MARKER not in blob
    assert PINNED_GROK_CANARY_PROMPT not in blob
    assert any(event.get("canary_identity") == "synthetic-live-canary" for event in progress)

    idle = backend.run_synthetic_live_canary()
    assert idle["status"] == "not_requested"
    assert idle["canary_identity"] == "synthetic-live-canary"
    assert idle["live_canary"] is False
