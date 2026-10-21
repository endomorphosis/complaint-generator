"""Pinned Grok 4.7 route contract.

Deterministic tests inject the provider and a fresh router trace. They never
treat that injection, or a response-cache trace, as a live canary.
"""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from types import SimpleNamespace

import pytest

import integrations.ipfs_datasets.llm as llm
from integrations.ipfs_accelerate.routers import (
    INFERENCE_OWNER,
    PINNED_GROK_CANARY_PROMPT,
    PINNED_GROK_MODEL,
    PINNED_GROK_PROVIDER,
    pinned_grok47_dispatch_kwargs,
)

MARKER = "synthetic-prompt-marker-route01"
TOKEN = "synthetic-secret-token-route01"


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)


def _assert_quiet(payload: dict) -> None:
    encoded = _dumps(payload)
    assert MARKER not in encoded
    assert TOKEN not in encoded
    assert "prompt" not in payload or payload.get("prompt") in ("", None)
    request_id = str(payload.get("request_id") or "")
    assert request_id
    assert request_id != hashlib.sha256(MARKER.encode("utf-8")).hexdigest()
    assert MARKER not in request_id


def _ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "grok_cli_binary_present", lambda: True)
    monkeypatch.setattr(llm, "grok_cli_auth_present", lambda: True)


def _trace(provider: str = PINNED_GROK_PROVIDER, model: str = PINNED_GROK_MODEL) -> dict[str, str]:
    return {"effective_provider_name": provider, "effective_model_name": model, "prompt": MARKER, "secret": TOKEN}


@pytest.fixture
def external_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"socket": 0, "process": 0, "prepare": 0, "generate": 0}

    def _socket(*_args, **_kwargs):
        calls["socket"] += 1
        raise AssertionError("network")

    def _popen(*_args, **_kwargs):
        calls["process"] += 1
        raise AssertionError("process")

    def _prepare(*_args, **_kwargs):
        calls["prepare"] += 1
        raise AssertionError("prepare")

    monkeypatch.setattr(socket, "socket", _socket)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    monkeypatch.setattr(llm, "_prepare_generate_text_call", _prepare)
    return calls


def test_static_capability_and_status_do_not_dispatch(monkeypatch, external_io):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: external_io.__setitem__("generate", external_io["generate"] + 1))
    status = llm.llm_router_status(
        provider="hf_router",
        model_name="arch-router",
        prompt=MARKER,
        perform_probe=False,
        base_url="hf-router.local",
        arch_router_routes=[{"name": "other", "model": "other-model"}],
    )
    receipt = llm.grok47_route_capability(include_canary=False, canary_transport=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("canary")))
    assert status["static_capability_only"] is True
    assert status["dispatch"] == "none"
    assert status["probe_performed"] is False
    assert receipt["static_capability_only"] is True
    assert receipt["canary_enabled"] is False
    assert receipt["live_canary"] is False
    assert receipt["dispatch"] == "none"
    assert receipt["inference_owner"] == INFERENCE_OWNER
    assert external_io == {"socket": 0, "process": 0, "prepare": 0, "generate": 0}
    _assert_quiet(receipt)


def test_capability_reports_missing_binary_auth_and_router(monkeypatch):
    monkeypatch.setattr(llm, "grok_cli_binary_present", lambda: False)
    monkeypatch.setattr(llm, "grok_cli_auth_present", lambda: False)
    monkeypatch.setattr(llm, "generate_text", None)
    called = {"transport": 0}

    def transport(**_kwargs):
        called["transport"] += 1
        return "GROK47_CANARY_OK"

    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=transport)
    assert called["transport"] == 0
    assert receipt["status"] == "unavailable"
    assert receipt["resumable"] is True
    assert receipt["router_symbol_available"] is False
    assert receipt["binary_available"] is False
    assert receipt["auth_present"] is False
    assert receipt["selected_provider_name"] == ""
    assert "grok binary not found on PATH" in receipt["error"]
    assert "missing authentication" in receipt["error"]
    assert "llm_router symbol is unavailable" in receipt["error"]
    assert receipt["live_canary"] is False
    _assert_quiet(receipt)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        (PINNED_GROK_PROVIDER, ""),
        (PINNED_GROK_PROVIDER, "grok-4"),
        (PINNED_GROK_PROVIDER, "grok-4.7-latest"),
        ("grok-cli", PINNED_GROK_MODEL),
        ("grok", PINNED_GROK_MODEL),
        ("xai", PINNED_GROK_MODEL),
        ("codex_cli", PINNED_GROK_MODEL),
        ("openrouter", PINNED_GROK_MODEL),
    ],
)
def test_unpinned_routes_are_refused_before_dispatch(monkeypatch, provider, model):
    calls = []

    def provider_call(**kwargs):
        calls.append(kwargs)
        return "should-not-run"

    monkeypatch.setattr(llm, "generate_text", provider_call)
    result = llm.generate_text_with_metadata(f"{MARKER} {TOKEN}", provider=provider, model_name=model)
    assert calls == []
    assert result["status"] == "unavailable"
    assert result["resumable"] is True
    assert result["dispatch"] == "none"
    assert result["live_canary"] is False
    assert "only admitted route" in result["error"]
    _assert_quiet(result)
    with pytest.raises(RuntimeError) as raised:
        llm.generate_text_via_router(f"{MARKER} {TOKEN}", provider=provider, model_name=model)
    assert MARKER not in str(raised.value)
    assert TOKEN not in str(raised.value)


def test_injected_provider_is_exact_and_not_a_live_canary(monkeypatch):
    calls = []

    def provider_call(**kwargs):
        calls.append(kwargs)
        return "synthetic-ok"

    monkeypatch.setattr(llm, "generate_text", provider_call)
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    result = llm.generate_text_with_metadata(
        f"{MARKER} {TOKEN}",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
    )
    assert result["status"] == "available"
    assert result["text"] == "synthetic-ok"
    assert len(calls) == 1
    assert calls[0]["provider"] == PINNED_GROK_PROVIDER
    assert calls[0]["model_name"] == PINNED_GROK_MODEL
    assert calls[0]["allow_local_fallback"] is False
    assert calls[0]["allow_cross_provider_fallback"] is False
    assert calls[0]["prompt"] == f"{MARKER} {TOKEN}"
    assert result["requested_provider_name"] == PINNED_GROK_PROVIDER
    assert result["effective_provider_name"] == PINNED_GROK_PROVIDER
    assert result["observed_provider_name"] == PINNED_GROK_PROVIDER
    assert result["observed_model_name"] == PINNED_GROK_MODEL
    assert result["route_observation"] == "verified"
    assert result["route_evidence_class"] == "router_selection"
    assert result["live_canary"] is False
    assert result["provider_reported_model"] == ""
    assert "secret" not in result
    assert result["inference_owner"] == INFERENCE_OWNER
    _assert_quiet(result)


def test_missing_or_mismatched_trace_is_not_rewritten(monkeypatch):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "synthetic-ok")
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: {})
    missing = llm.generate_text_with_metadata("ok", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert missing["status"] == "available"
    assert missing["route_observation"] == "unverified"
    assert missing["live_canary"] is False

    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace("codex_cli", "grok-4"))
    mismatched = llm.generate_text_with_metadata("ok", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert mismatched["route_observation"] == "mismatched"
    assert mismatched["observed_provider_name"] == "codex_cli"
    assert mismatched["observed_model_name"] == "grok-4"
    assert mismatched["effective_provider_name"] == PINNED_GROK_PROVIDER
    assert mismatched["live_canary"] is False
    assert mismatched["text"] == "synthetic-ok"


@pytest.mark.parametrize("setup", ["preflight", "provider"])
def test_generation_error_branches_stay_unavailable_and_quiet(monkeypatch, setup):
    calls = []

    def native(**kwargs):
        calls.append(kwargs)
        raise RuntimeError(f"provider echoed {kwargs.get('prompt', '')} {TOKEN}")

    native.__module__ = "ipfs_accelerate_py.llm_router"
    monkeypatch.setattr(llm, "generate_text", native)
    _ready(monkeypatch)
    if setup == "preflight":
        monkeypatch.setattr(llm, "_provider_preflight_error", lambda **_kwargs: f"{MARKER} {TOKEN}")
    result = llm.generate_text_with_metadata(
        f"{MARKER} {TOKEN}",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
    )
    assert result["status"] == "unavailable"
    assert result["resumable"] is True
    assert result["live_canary"] is False
    assert result["text"] == ""
    if setup == "preflight":
        assert calls == []
        assert result["dispatch"] == "none"
        assert result["error"] == "provider_exception"
    else:
        assert len(calls) == 1
        assert result["error"] == "provider_exception"
        assert result["dispatch"] == "attempted"
    _assert_quiet(result)


@pytest.mark.parametrize("gap", ["binary", "auth"])
def test_capability_blocks_canary_when_binary_or_auth_is_missing(monkeypatch, gap):
    _ready(monkeypatch)
    if gap == "binary":
        monkeypatch.setattr(llm, "grok_cli_binary_present", lambda: False)
    else:
        monkeypatch.setattr(llm, "grok_cli_auth_present", lambda: False)
    calls = {"transport": 0}

    def transport(**_kwargs):
        calls["transport"] += 1
        return {"text": PINNED_GROK_CANARY_PROMPT, "dispatch": "live", "end": {"modelUsage": {PINNED_GROK_MODEL: {}}}}

    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=transport)
    assert calls["transport"] == 0
    assert receipt["status"] == "unavailable"
    assert receipt["resumable"] is True
    assert receipt["live_canary"] is False
    assert receipt["dispatch"] == "none"
    if gap == "binary":
        assert receipt["binary_available"] is False
        assert "grok binary not found on PATH" in receipt["error"]
    else:
        assert receipt["auth_present"] is False
        assert "missing authentication" in receipt["error"]
    _assert_quiet(receipt)


def test_native_router_pins_model_without_fallback(monkeypatch):
    import ipfs_accelerate_py.llm_router as router

    calls = []

    class Primary:
        def generate(self, prompt, *, model_name=None, **kwargs):
            calls.append((prompt, model_name, kwargs))
            return "native-synthetic"

    def get_provider(name, **_kwargs):
        assert name == PINNED_GROK_PROVIDER
        return Primary()

    monkeypatch.setattr(router, "get_default_router_deps", lambda: SimpleNamespace())
    monkeypatch.setattr(router, "get_llm_provider", get_provider)
    monkeypatch.setattr(router, "_iter_unpinned_optional_providers", lambda: iter([("openrouter", Primary())]))
    monkeypatch.setattr(router, "_response_cache_enabled", lambda: False)
    monkeypatch.setattr(llm, "generate_text", router.generate_text)
    _ready(monkeypatch)
    result = llm.generate_text_with_metadata(
        f"{MARKER} {TOKEN}",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
    )
    assert pinned_grok47_dispatch_kwargs() == {
        "provider": PINNED_GROK_PROVIDER,
        "model_name": PINNED_GROK_MODEL,
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
    }
    assert len(calls) == 1
    _prompt, model_name, kwargs = calls[0]
    assert model_name == PINNED_GROK_MODEL
    assert kwargs.get("allow_local_fallback") is not True
    assert kwargs.get("allow_cross_provider_fallback") is not True
    assert _prompt == f"{MARKER} {TOKEN}"
    assert result["status"] == "available"
    assert result["route_observation"] == "verified"
    assert result["live_canary"] is False
    assert result["provider_reported_model"] == ""
    _assert_quiet(result)


def test_opt_in_canary_records_wire_model_only_when_live(monkeypatch):
    _ready(monkeypatch)
    seen = {}

    def transport(**kwargs):
        seen.update(kwargs)
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "dispatch": "live",
            "end": {"modelUsage": {PINNED_GROK_MODEL: {"outputTokens": 1, "prompt": MARKER}}},
            "prompt": MARKER,
            "secret": TOKEN,
        }

    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=transport)
    assert seen["prompt"] == PINNED_GROK_CANARY_PROMPT
    assert seen["provider"] == PINNED_GROK_PROVIDER
    assert seen["model_name"] == PINNED_GROK_MODEL
    assert seen["allow_local_fallback"] is False
    assert seen["allow_cross_provider_fallback"] is False
    assert seen["max_tokens"] == 16
    assert seen["grok_max_turns"] == 1
    assert "tools" not in seen
    assert receipt["status"] == "available"
    assert receipt["live_canary"] is True
    assert receipt["provider_reported_model"] == PINNED_GROK_MODEL
    assert receipt["canary_token_matched"] is True
    assert receipt["static_capability_only"] is False
    _assert_quiet(receipt)

    def injected(**_kwargs):
        return PINNED_GROK_CANARY_PROMPT

    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    injected_receipt = llm.grok47_route_capability(include_canary=True, canary_transport=injected)
    assert injected_receipt["status"] == "unverified"
    assert injected_receipt["live_canary"] is False
    assert injected_receipt["provider_reported_model"] == ""
    assert injected_receipt["route_observation"] == "verified"
    assert injected_receipt["route_evidence_class"] == "router_selection"

    def cached(**_kwargs):
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "dispatch": "live",
            "cache_hit": True,
            "end": {"modelUsage": {PINNED_GROK_MODEL: {"outputTokens": 1}}},
        }

    cached_receipt = llm.grok47_route_capability(include_canary=True, canary_transport=cached)
    assert cached_receipt["live_canary"] is False
    assert cached_receipt["response_cache_hit"] is True
    assert cached_receipt["provider_reported_model"] == ""
    assert cached_receipt["status"] == "unverified"

    def wrong_model(**_kwargs):
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "dispatch": "live",
            "end": {"modelUsage": {"grok-4": {"outputTokens": 1}}},
        }

    refused = llm.grok47_route_capability(include_canary=True, canary_transport=wrong_model)
    assert refused["status"] == "unavailable"
    assert refused["resumable"] is True
    assert refused["live_canary"] is True
    assert refused["provider_reported_model"] == "grok-4"
    assert refused["canary_token_matched"] is True

    def explode(**kwargs):
        raise RuntimeError(kwargs["prompt"] + TOKEN)

    exploded = llm.grok47_route_capability(include_canary=True, canary_transport=explode)
    assert exploded["status"] == "unavailable"
    assert exploded["error"] == "provider_exception"
    assert exploded["resumable"] is True
    assert exploded["live_canary"] is False
    _assert_quiet(exploded)


def test_disabled_canary_does_not_use_a_ready_transport(monkeypatch):
    _ready(monkeypatch)

    def transport(**_kwargs):
        raise AssertionError("canary dispatched")

    receipt = llm.grok47_route_capability(include_canary=False, canary_transport=transport)
    assert receipt["status"] == "available"
    assert receipt["canary_enabled"] is False
    assert receipt["live_canary"] is False
    assert receipt["static_capability_only"] is True
    assert receipt["selected_provider_name"] == PINNED_GROK_PROVIDER
    assert receipt["selected_model_name"] == PINNED_GROK_MODEL
