"""No-paid-call intake router contract. Fakes never contact a provider."""

import json
import subprocess
import sys
import threading
import time
import uuid

import pytest

import integrations.ipfs_datasets.llm as llm
from backends.llm_router_backend import LLMRouterBackend, ProviderRouteError
from integrations.ipfs_accelerate.routers import PINNED_GROK_MODEL, PINNED_GROK_PROVIDER
from integrations.ipfs_datasets.llm import (
    intake_request_response_format,
    parse_intake_request,
)
from mediator.mediator import Mediator

SECRET = "PRIVATE_NARRATIVE_SHOULD_NOT_LEAK"
SOURCE = "José paid"


def _request_id():
    return uuid.uuid4().hex


def _body(request_id, operation="extract_facts", questions=None, facts=None):
    return json.dumps({
        "schema_version": "intake_request_v1",
        "operation": operation,
        "request_id": request_id,
        "questions": questions or [],
        "facts": facts or [],
    }, separators=(",", ":"))


def _fact():
    encoded = SOURCE.encode("utf-8")
    value = "José"
    assert encoded[:len(value.encode())] == value.encode()
    return {
        "field": "party",
        "value": value,
        "source_start": 0,
        "source_end": len(value.encode("utf-8")),
        "target_ref": "party.complainant",
    }


def _backend(**overrides):
    options = dict(retry_max_attempts=3, retry_backoff_base_s=5, retry_backoff_max_s=5,
                   retry_jitter_s=0, timeout_seconds=0.25, intake_operation="extract_facts")
    options.update(overrides)
    return LLMRouterBackend("intake-router", provider=PINNED_GROK_PROVIDER, model=PINNED_GROK_MODEL, **options)


def _patch_native(monkeypatch, fn):
    monkeypatch.setattr(llm, "generate_text", fn)
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: {
        "effective_provider_name": PINNED_GROK_PROVIDER,
        "effective_model_name": PINNED_GROK_MODEL,
        "router_version": "router-test-1",
        "prompt": SECRET,
        "api_key": "sk-secret",
        "error": SECRET,
    })


def _assert_pinned(call):
    assert call["provider"] == PINNED_GROK_PROVIDER
    assert call["model_name"] == PINNED_GROK_MODEL
    assert call["allow_local_fallback"] is False
    assert call["allow_cross_provider_fallback"] is False
    schema = call["response_format"]
    assert schema["type"] == "json_schema"
    assert schema["json_schema"]["name"] == "intake_request_v1"
    assert schema["json_schema"]["strict"] is True
    assert schema["json_schema"]["schema"]["type"] == "object"


def test_response_format_matches_native_strict_shape():
    fmt = intake_request_response_format()
    assert set(fmt) == {"type", "json_schema"}
    assert set(fmt["json_schema"]) == {"name", "strict", "schema"}


def test_quota_failure_dispatches_pinned_model_once(monkeypatch):
    calls = []

    def native(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("quota exceeded " + SECRET)

    _patch_native(monkeypatch, native)
    backend = _backend()
    with pytest.raises(ProviderRouteError) as caught:
        backend(SECRET, intake_source_text=SOURCE)
    assert caught.value.payload["error_code"] == "quota"
    assert caught.value.payload["status"] == "quota"
    assert caught.value.payload["intake_complete"] is False
    assert len(calls) == 1
    _assert_pinned(calls[0])
    assert calls[0]["model_name"] is not None
    blob = json.dumps(caught.value.payload)
    assert SECRET not in blob
    assert "sk-secret" not in blob
    assert caught.value.payload["request_id"]
    assert caught.value.payload["prompt_logged"] is False


def test_total_retry_budget_does_not_open_another_model(monkeypatch):
    calls = []

    def native(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("temporarily unavailable")

    _patch_native(monkeypatch, native)
    backend = _backend()
    started = time.monotonic()
    with pytest.raises(ProviderRouteError) as caught:
        backend("synthetic", intake_source_text=SOURCE)
    elapsed = time.monotonic() - started
    assert caught.value.payload["error_code"] in {"provider_unavailable", "timeout"}
    assert len(calls) == 1
    assert elapsed < 1.0
    _assert_pinned(calls[0])


def test_cancel_kills_owned_child(monkeypatch):
    started = threading.Event()
    children = []

    def native(**kwargs):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        children.append(proc)
        backend.note_owned_child(proc.pid)
        started.set()
        proc.wait()
        raise RuntimeError("provider still running")

    _patch_native(monkeypatch, native)
    backend = _backend(timeout_seconds=5)
    holder = {}

    def run():
        try:
            backend("synthetic", intake_source_text=SOURCE)
        except ProviderRouteError as exc:
            holder["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(2)
    backend.cancel()
    thread.join(2)
    assert not thread.is_alive()
    assert holder["error"].payload["error_code"] == "cancelled"
    assert children[0].poll() is not None
    assert SECRET not in json.dumps(holder["error"].payload)


def test_schema_and_span_rejection_leaves_graph_unchanged():
    mediator = Mediator([lambda prompt, **kwargs: prompt])
    request_id = _request_id()
    mediator.intake_model_suggestions = [{"kind": "fact", "record_type": "model_suggestion", "value": "kept"}]
    mediator.legal_records = [{"record_type": "legal", "citation": "synthetic-statute"}]
    before_suggestions = list(mediator.intake_model_suggestions)
    before_legal = list(mediator.legal_records)
    fenced = "```json\n" + _body(request_id, facts=[_fact()]) + "\n```"
    duplicate = '{"schema_version":"intake_request_v1","schema_version":"intake_request_v1"}'
    bad_span = _body(request_id, facts=[{**_fact(), "source_end": 1}])
    for raw in (fenced, duplicate, bad_span, "not json"):
        outcome = mediator.apply_intake_router_output(
            raw, operation="extract_facts", source_text=SOURCE, request_id=request_id,
        )
        assert outcome["applied"] is False
        assert outcome["graph_changed"] is False
        assert outcome["intake_complete"] is False
        assert mediator.intake_model_suggestions == before_suggestions
        assert mediator.legal_records == before_legal
    with pytest.raises(llm.IntakeContractError):
        parse_intake_request(bad_span, request_id=request_id, operation="extract_facts", source_text=SOURCE)


def test_valid_span_is_suggestion_and_successful_empty_does_not_finish_intake():
    mediator = Mediator([lambda prompt, **kwargs: prompt])
    request_id = mediator._session_router_request_id()
    mediator.legal_records = [{"record_type": "legal", "citation": "synthetic-statute"}]
    applied = mediator.apply_intake_router_output(
        _body(request_id, facts=[_fact()]),
        operation="extract_facts",
        source_text=SOURCE,
        request_id=request_id,
    )
    assert applied["applied"] is True
    assert applied["intake_complete"] is False
    assert applied["graph_changed"] is True
    assert mediator.intake_complete is False
    assert mediator.intake_model_suggestions[-1]["record_type"] == "model_suggestion"
    assert mediator.intake_model_suggestions[-1]["value"] == "José"
    assert mediator.legal_records == [{"record_type": "legal", "citation": "synthetic-statute"}]
    empty = mediator.apply_intake_router_output(
        _body(request_id, operation="propose_questions"),
        operation="propose_questions",
        source_text=SOURCE,
        request_id=request_id,
    )
    assert empty["successful_empty"] is True
    assert empty["intake_complete"] is False
    assert empty["graph_changed"] is False


def test_redacted_trace_and_request_id_propagate(monkeypatch):
    request_id = _request_id()
    calls = []

    def native(**kwargs):
        calls.append(kwargs)
        return _body(request_id, facts=[_fact()])

    _patch_native(monkeypatch, native)
    backend = _backend(timeout_seconds=2)
    text = backend(SECRET, intake_request_id=request_id, intake_source_text=SOURCE)
    parsed = json.loads(text)
    assert parsed["request_id"] == request_id
    assert len(calls) == 1
    _assert_pinned(calls[0])
    receipt = backend.task_receipts[-1]
    assert receipt["request_id"] == request_id
    assert receipt["prompt_logged"] is False
    assert receipt["intake_complete"] is False
    assert receipt["error_code"] == ""
    blob = json.dumps(receipt)
    assert SECRET not in blob
    assert "sk-secret" not in blob
    meta = backend.last_result_metadata
    assert meta["request_id"] == request_id
    assert meta["configured_provider_name"] == PINNED_GROK_PROVIDER
    assert meta["observed_provider_name"] == PINNED_GROK_PROVIDER
    assert meta["observed_model_name"] == PINNED_GROK_MODEL
    assert meta["router_version"] == "router-test-1"
    assert SECRET not in json.dumps({key: value for key, value in meta.items() if key != "text"})

    mediator = Mediator([backend])
    mediator._router_request_id = request_id
    mediator.intake_model_suggestions = []
    mediator.legal_records = [{"record_type": "legal"}]

    def forwarding(prompt, **kwargs):
        assert kwargs["intake_request_id"] == request_id
        return backend(prompt, **kwargs)

    mediator.backends = [forwarding]
    outcome = mediator.intake_router_exchange("synthetic", operation="extract_facts", source_text=SOURCE)
    assert outcome["applied"] is True
    assert outcome["intake_complete"] is False
    assert outcome["request_id"] == request_id
    logged = json.dumps(mediator.state.log)
    assert SECRET not in logged
    assert request_id in logged
    assert "sk-secret" not in logged


def test_exchange_failure_does_not_change_graph(monkeypatch):
    def native(**kwargs):
        raise RuntimeError("llm_router_unavailable")

    _patch_native(monkeypatch, native)
    backend = _backend(retry_max_attempts=1, timeout_seconds=1)
    mediator = Mediator([backend])
    mediator.intake_model_suggestions = [{"kept": True}]
    mediator.legal_records = [{"record_type": "legal"}]
    outcome = mediator.intake_router_exchange(SECRET, operation="extract_facts", source_text=SOURCE)
    assert outcome["applied"] is False
    assert outcome["graph_changed"] is False
    assert outcome["intake_complete"] is False
    assert outcome["error_code"] in {"provider_unavailable", "timeout", "quota", "malformed_output"}
    assert mediator.intake_model_suggestions == [{"kept": True}]
    assert mediator.legal_records == [{"record_type": "legal"}]
    assert SECRET not in json.dumps(mediator.state.log)


def test_distinct_failure_kinds(monkeypatch):
    seen = {}

    def run(message):
        def native(**kwargs):
            raise RuntimeError(message)
        _patch_native(monkeypatch, native)
        backend = _backend(retry_max_attempts=1, timeout_seconds=1)
        with pytest.raises(ProviderRouteError) as caught:
            backend("synthetic", intake_source_text=SOURCE)
        seen[message] = caught.value.payload["error_code"]

    run("quota exceeded")
    run("does not match the requested schema")
    assert seen["quota exceeded"] == "quota"
    assert seen["does not match the requested schema"] == "malformed_output"
    assert seen["quota exceeded"] != seen["does not match the requested schema"]
