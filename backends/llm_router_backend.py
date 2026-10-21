"""LLM Router Backend."""

import json
import logging
import os
import random
import time
import threading
import uuid

from integrations.ipfs_accelerate.routers import (
    COMPLAINT_PROVIDER_ALIASES,
    INFERENCE_OWNER,
    PINNED_GROK_CANARY_PROMPT,
    PINNED_GROK_MODEL,
    PINNED_GROK_PROVIDER,
    unpinned_grok_route_reason,
)
from integrations.ipfs_datasets.llm import (
    LLM_ROUTER_AVAILABLE,
    generate_text_via_router as generate_text,
    generate_text_with_metadata,
    grok47_route_capability,
)

logger = logging.getLogger(__name__)

_PROVIDER_ALIASES = COMPLAINT_PROVIDER_ALIASES

_PROVIDER_ENV_KEYS = (
    'IPFS_DATASETS_PY_LLM_PROVIDER',
    'COMPLAINT_GENERATOR_LLM_PROVIDER',
    'LLM_ROUTER_PROVIDER',
)

# Provider-reported build label accepted for the pinned grok-4.7 route.
SUPPORTED_GROK_47_IDENTITIES = frozenset({PINNED_GROK_MODEL, "grok-4.7-build"})
SYNTHETIC_LIVE_CANARY_IDENTITY = "synthetic-live-canary"
REMOTE_PROVIDERS = frozenset({
    PINNED_GROK_PROVIDER,
    "openai",
    "codex",
    "codex_cli",
    "openrouter",
    "anthropic",
    "gemini",
    "gemini_cli",
    "huggingface_router",
    "hf_router",
    "huggingface_inference",
    "hf_inference_api",
})

_ERROR_TEXT = {
    "provider_unavailable": "Grok 4.7 is unavailable. No Codex or other model was substituted.",
    "substitution_refused": "Refusing a provider or model other than grok_cli/grok-4.7. The session was retained.",
    "route_unverified": "Grok 4.7 selection was not verified against a provider-supported identity.",
    "timeout": "The Grok 4.7 request exceeded its deadline. The session was retained.",
    "cancelled": "The Grok 4.7 request was cancelled. The session was retained.",
    "malformed_output": "Structured output validation failed. The session was retained.",
    "unpinned_route": "Refusing an unpinned Grok route. No substitute model was contacted.",
}


class ProviderRouteError(Exception):
    """Bounded provider failure. The message never includes prompt text."""

    def __init__(self, payload):
        self.payload = dict(payload)
        super().__init__("llm_router_error: " + json.dumps(self.payload, sort_keys=True, default=str))


class LLMRouterBackend:
    """Backend that uses ipfs_datasets_py's llm_router for LLM routing."""

    def __init__(self, id, provider=None, model=None, **config):
        """
        Initialize the LLM Router Backend.

        Args:
            id: Backend identifier
            provider: Optional provider name (e.g., 'openrouter', 'local_hf')
            model: Optional model name
            **config: Additional configuration passed to generate_text
        """
        self.id = id
        raw_provider = self._resolve_provider_name(provider)
        self.provider = _PROVIDER_ALIASES.get(raw_provider.lower(), raw_provider) if raw_provider else None
        if model is None:
            if self.provider in {'codex', 'codex_cli'}:
                self.model = 'gpt-5.3-codex'
            elif str(self.provider).strip().lower() in {'hf', 'local_hf', 'hf_inference', 'hf_router', 'huggingface_inference', 'huggingface_router'}:
                self.model = (
                    os.getenv('LLM_ROUTER_FALLBACK_MODEL', '').strip()
                    or os.getenv('IPFS_DATASETS_PY_OPENROUTER_MODEL', '').strip()
                    or os.getenv('IPFS_DATASETS_PY_LLM_MODEL', '').strip()
                    or None
                )
            elif self.provider:
                self.model = (
                    os.getenv('IPFS_DATASETS_PY_LLM_MODEL', '').strip()
                    or os.getenv('COMPLAINT_GENERATOR_LLM_MODEL', '').strip()
                    or os.getenv('LLM_ROUTER_MODEL', '').strip()
                    or None
                )
            else:
                self.model = None
        else:
            self.model = model

        self.retry_max_attempts = int(config.pop('retry_max_attempts', 1) or 1)
        self.retry_backoff_base_s = float(config.pop('retry_backoff_base_s', 0.5) or 0.5)
        self.retry_backoff_max_s = float(config.pop('retry_backoff_max_s', 20.0) or 20.0)
        self.retry_jitter_s = float(config.pop('retry_jitter_s', 0.1) or 0.1)
        self.retryable_error_substrings = list(
            config.pop(
                'retryable_error_substrings',
                [
                    '429',
                    'rate limit',
                    'too many requests',
                    'temporarily unavailable',
                    'timeout',
                    'timed out',
                    'econnreset',
                    'connection reset',
                    'connection aborted',
                    'service unavailable',
                ],
            )
        )
        self.timeout_seconds = config.pop('timeout_seconds', config.pop('timeout', None))
        if self.timeout_seconds is not None:
            self.timeout_seconds = float(self.timeout_seconds)
        self.structured_output = bool(config.pop('structured_output', False))
        schema = config.pop('response_schema', None)
        self.response_schema_required = []
        if isinstance(schema, dict):
            required = schema.get("required", [])
            if isinstance(required, list):
                self.response_schema_required = [str(item) for item in required]
        elif isinstance(schema, list):
            self.response_schema_required = [str(item) for item in schema]
        self.forbid_model_substitution = config.pop('forbid_model_substitution', None)
        self.progress_callback = config.pop('progress_callback', None)
        self._cancel_event = config.pop('cancel_event', None) or threading.Event()

        self.config = config
        self.session_id = uuid.uuid4().hex
        self.session_retained = True
        self.progress_events = []
        self.task_receipts = []
        self.last_result_metadata = None

        self._stats_lock = threading.Lock()
        self._retry_stats = {
            'calls_total': 0,
            'attempts_total': 0,
            'retries_total': 0,
            'backoff_seconds_total': 0.0,
            'failures_total': 0,
        }

        if not LLM_ROUTER_AVAILABLE:
            raise ImportError(
                "llm_router not available. Please ensure ipfs_datasets_py submodule "
                "is initialized with: git submodule update --init --recursive"
            )

    @property
    def pinned_grok47(self) -> bool:
        return self.provider == PINNED_GROK_PROVIDER and self.model == PINNED_GROK_MODEL

    def remote_inference_disclosure(self) -> dict:
        """State whether this route sends complaint text off-box.

        Encryption at rest covers stored snapshots. It does not make a remote
        provider call private.
        """

        provider_name = str(self.provider or "")
        sends_remotely = provider_name in REMOTE_PROVIDERS or provider_name.lower().startswith("grok")
        return {
            "requested_provider": provider_name,
            "requested_model": str(self.model or ""),
            "sends_complaint_text_remotely": bool(sends_remotely),
            "encryption_at_rest_implies_private_remote_inference": False,
            "explanation": (
                "A grok_cli/grok-4.7 request sends the generation prompt, including any complaint text placed in that prompt, to the remote Grok provider. "
                "Encryption at rest protects stored session snapshots and does not make that remote inference private. "
                "Local-private processing does not send complaint text to a remote provider."
                if sends_remotely
                else "This provider is treated as local. Complaint text in the prompt is not described as a remote Grok inference. Encryption at rest still does not imply private remote inference."
            ),
        }

    def cancel(self) -> None:
        self._cancel_event.set()

    def configuration_receipt(self) -> dict:
        receipt = self._receipt(
            status="configured",
            error_code="",
            selected_provider="",
            selected_model="",
            route_observation="not_dispatched",
            provider_supported_identity=False,
            request_id="",
        )
        return receipt

    def sanitized_session_diagnostics(self) -> dict:
        latest = self.task_receipts[-1] if self.task_receipts else self.configuration_receipt()
        return {
            "session_id": self.session_id,
            "session_retained": True,
            "router": INFERENCE_OWNER,
            "requested_router": INFERENCE_OWNER,
            "selected_router": latest.get("selected_router") or "",
            "requested_provider": str(self.provider or ""),
            "selected_provider": latest.get("selected_provider") or "",
            "requested_model": str(self.model or ""),
            "selected_model": latest.get("selected_model") or "",
            "route_observation": latest.get("route_observation") or "not_dispatched",
            "provider_supported_identity": bool(latest.get("provider_supported_identity")),
            "status": latest.get("status") or "configured",
            "error_code": latest.get("error_code") or "",
            "prompt_logged": False,
            "live_canary": False,
            "remote_inference": self.remote_inference_disclosure(),
        }

    def task_receipt_snapshot(self) -> list:
        if self.task_receipts:
            return [dict(item) for item in self.task_receipts]
        return [self.configuration_receipt()]

    @staticmethod
    def _resolve_provider_name(provider):
        explicit_provider = str(provider or '').strip()
        if explicit_provider:
            return explicit_provider
        for key in _PROVIDER_ENV_KEYS:
            value = str(os.getenv(key, '')).strip()
            if value:
                return value
        return ''

    def __call__(self, text, **kwargs):
        """
        Generate text using the llm_router.

        Args:
            text: The prompt text

        Returns:
            Generated text response
        """
        with self._stats_lock:
            self._retry_stats['calls_total'] += 1

        privacy_context = kwargs.get("complaint_privacy_context")
        route_block = unpinned_grok_route_reason(self.provider, self.model)
        if route_block or (self._strict_route() and not self.pinned_grok47):
            self._fail("unpinned_route", route_observation="refused", selected_provider="", selected_model="")

        last_error = None
        max_attempts = max(1, self.retry_max_attempts)
        deadline = None
        if self._strict_route() and self.timeout_seconds is not None:
            deadline = time.monotonic() + float(self.timeout_seconds)
        for attempt in range(1, max_attempts + 1):
            self._raise_if_cancelled()
            if deadline is not None and time.monotonic() >= deadline:
                self._fail("timeout", route_observation="timeout")
            with self._stats_lock:
                self._retry_stats['attempts_total'] += 1
            self._emit_progress({"phase": "provider_wait", "attempt": attempt, "max_attempts": max_attempts, "router": INFERENCE_OWNER})
            try:
                metadata_payload = self._generate(text, privacy_context=privacy_context, deadline=deadline)
                if str(metadata_payload.get("status") or "").strip().lower() != "available":
                    raise ProviderRouteError(self._record(
                        status="unavailable",
                        error_code="provider_unavailable",
                        metadata=metadata_payload,
                        route_observation="unavailable",
                        provider_supported_identity=False,
                    ))
                self._reject_substitution(metadata_payload)
                response = str(metadata_payload.get("text") or "")
                response = self._validate_structured(response)
                self.last_result_metadata = dict(metadata_payload)
                self._record(
                    status="available",
                    error_code="",
                    metadata=metadata_payload,
                    route_observation=self._observation(metadata_payload),
                    provider_supported_identity=self._identity_supported(metadata_payload),
                )
                self._emit_progress({"phase": "provider_done", "attempt": attempt, "router": INFERENCE_OWNER, "status": "available"})
                return response
            except ProviderRouteError as error:
                last_error = error
                if error.payload.get("error_code") in {"substitution_refused", "route_unverified", "malformed_output", "cancelled", "timeout", "unpinned_route"}:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    raise
                retryable = self._is_retryable_error(error)
                if attempt >= max_attempts or not retryable:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    raise
            except Exception as error:
                last_error = error
                retryable = self._is_retryable_error(error)
                if attempt >= max_attempts or not retryable:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    if self._strict_route():
                        self._fail("provider_unavailable", route_observation="unavailable")
                    raise Exception(f'llm_router_error: {str(error)}')

            backoff_s = self._compute_backoff_seconds(attempt)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._fail("timeout", route_observation="timeout")
                backoff_s = min(backoff_s, remaining)
            with self._stats_lock:
                self._retry_stats['retries_total'] += 1
                self._retry_stats['backoff_seconds_total'] += float(backoff_s)
            self._emit_progress({"phase": "retry_backoff", "attempt": attempt, "router": INFERENCE_OWNER})
            self._sleep_interruptible(backoff_s, deadline)

        with self._stats_lock:
            self._retry_stats['failures_total'] += 1
        if isinstance(last_error, ProviderRouteError):
            raise last_error
        raise Exception(f'llm_router_error: {str(last_error)}')

    def run_synthetic_live_canary(self, *, transport=None, confirm_live=False):
        """Dispatch only the public synthetic canary token.

        This is not an interview turn. Complaint text is never forwarded.
        Injected transports stay labeled synthetic and are not rewritten as a
        native live canary.
        """

        if confirm_live is not True and transport is None:
            receipt = self._receipt(
                status="not_requested",
                error_code="",
                selected_provider="",
                selected_model="",
                route_observation="not_dispatched",
                provider_supported_identity=False,
                request_id="",
                canary_identity=SYNTHETIC_LIVE_CANARY_IDENTITY,
                live_canary=False,
            )
            self.task_receipts.append(receipt)
            return receipt
        from integrations.ipfs_accelerate.routers import pinned_grok47_canary_kwargs

        canary_kwargs = pinned_grok47_canary_kwargs()
        if transport is None:
            raise ProviderRouteError(self._receipt(
                status="error",
                error_code="provider_unavailable",
                selected_provider="",
                selected_model="",
                route_observation="unavailable",
                provider_supported_identity=False,
                request_id="",
                canary_identity=SYNTHETIC_LIVE_CANARY_IDENTITY,
            ))
        transport_result = transport(prompt=PINNED_GROK_CANARY_PROMPT, **canary_kwargs)
        capability = grok47_route_capability(include_canary=True, canary_transport=transport)
        extra_provider = ""
        extra_model = ""
        if isinstance(transport_result, dict):
            extra_provider = str(transport_result.get("selected_provider_name") or "")
            extra_model = str(transport_result.get("selected_model_name") or transport_result.get("provider_reported_model") or "")
        selected_provider = str(capability.get("selected_provider_name") or extra_provider)
        selected_model = str(capability.get("selected_model_name") or capability.get("provider_reported_model") or extra_model)
        supported = selected_provider == PINNED_GROK_PROVIDER and selected_model in SUPPORTED_GROK_47_IDENTITIES
        native_live = capability.get("live_canary") is True and supported
        receipt = self._receipt(
            status="available" if supported else str(capability.get("status") or "unverified"),
            error_code="" if supported else str(capability.get("error") or "route_unverified"),
            selected_provider=selected_provider,
            selected_model=selected_model,
            route_observation="verified" if supported else str(capability.get("route_observation") or "unverified"),
            provider_supported_identity=supported,
            request_id=str(capability.get("request_id") or ""),
            canary_identity=SYNTHETIC_LIVE_CANARY_IDENTITY,
            live_canary=bool(native_live),
        )
        receipt["canary_prompt_class"] = "synthetic_public_token"
        receipt["complaint_data_included"] = False
        receipt["evidence_class"] = "native_live_canary" if native_live else "synthetic_canary"
        self.task_receipts.append(receipt)
        self._emit_progress({"phase": "synthetic_canary", "router": INFERENCE_OWNER, "canary_identity": SYNTHETIC_LIVE_CANARY_IDENTITY})
        return receipt

    def _strict_route(self) -> bool:
        if self.forbid_model_substitution is not None:
            return bool(self.forbid_model_substitution)
        provider_name = str(self.provider or "").lower()
        model_name = str(self.model or "").lower()
        return provider_name.startswith("grok") or model_name.startswith("grok") or self.pinned_grok47

    def _generate(self, text, *, privacy_context, deadline):
        call_kwargs = dict(self.config)
        if self.pinned_grok47:
            call_kwargs["allow_local_fallback"] = False
            call_kwargs["allow_cross_provider_fallback"] = False
        if privacy_context is not None:
            call_kwargs["complaint_privacy_context"] = privacy_context
        if deadline is not None:
            remaining = max(0.0, deadline - time.monotonic())
            call_kwargs["timeout"] = remaining
        if self._cancel_event.is_set():
            self._fail("cancelled", route_observation="cancelled")
        if not self._strict_route() or self.timeout_seconds is None:
            return generate_text_with_metadata(
                prompt=text,
                provider=self.provider,
                model_name=self.model,
                **call_kwargs,
            )
        holder = {}

        def _run():
            try:
                holder["result"] = generate_text_with_metadata(
                    prompt=text,
                    provider=self.provider,
                    model_name=self.model,
                    **call_kwargs,
                )
            except Exception as exc:
                holder["error"] = exc

        worker = threading.Thread(target=_run, name="llm-router-grok47", daemon=True)
        worker.start()
        remaining = max(0.0, deadline - time.monotonic()) if deadline is not None else float(self.timeout_seconds)
        worker.join(remaining)
        if worker.is_alive():
            self._cancel_event.set()
            self._fail("timeout", route_observation="timeout")
        if self._cancel_event.is_set() and "result" not in holder:
            self._fail("cancelled", route_observation="cancelled")
        if "error" in holder:
            raise holder["error"]
        return holder.get("result") or {}

    def _reject_substitution(self, metadata):
        if not self._strict_route():
            return
        observed_provider = str(metadata.get("observed_provider_name") or metadata.get("effective_provider_name") or "")
        observed_model = str(metadata.get("observed_model_name") or metadata.get("effective_model_name") or "")
        provider_ok = observed_provider in {"", PINNED_GROK_PROVIDER}
        model_ok = observed_model in {"", *SUPPORTED_GROK_47_IDENTITIES}
        if observed_provider and not provider_ok:
            self._fail(
                "substitution_refused",
                metadata=metadata,
                selected_provider=observed_provider,
                selected_model=observed_model,
                route_observation="mismatched",
            )
        if observed_model and not model_ok:
            self._fail(
                "substitution_refused",
                metadata=metadata,
                selected_provider=observed_provider,
                selected_model=observed_model,
                route_observation="mismatched",
            )
        if self.pinned_grok47 and (not observed_provider or not observed_model or not self._identity_supported(metadata)):
            self._fail(
                "route_unverified",
                metadata=metadata,
                selected_provider=observed_provider,
                selected_model=observed_model,
                route_observation="unverified",
            )

    def _identity_supported(self, metadata) -> bool:
        observed_provider = str(metadata.get("observed_provider_name") or "")
        observed_model = str(metadata.get("observed_model_name") or "")
        if observed_provider == PINNED_GROK_PROVIDER and observed_model in SUPPORTED_GROK_47_IDENTITIES:
            return True
        if not self.pinned_grok47:
            return bool(observed_provider and observed_model)
        return False

    def _observation(self, metadata) -> str:
        if self._identity_supported(metadata) and self.pinned_grok47:
            return "verified"
        return str(metadata.get("route_observation") or "unverified")

    def _validate_structured(self, text: str) -> str:
        if not self.structured_output:
            return text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            self._fail("malformed_output", route_observation="malformed")
        if not isinstance(payload, dict):
            self._fail("malformed_output", route_observation="malformed")
        missing = [key for key in self.response_schema_required if key not in payload]
        if missing:
            self._fail("malformed_output", route_observation="malformed")
        return text

    def _fail(self, error_code, *, metadata=None, selected_provider="", selected_model="", route_observation="unavailable"):
        if metadata is not None:
            selected_provider = selected_provider or str(metadata.get("observed_provider_name") or metadata.get("effective_provider_name") or "")
            selected_model = selected_model or str(metadata.get("observed_model_name") or metadata.get("effective_model_name") or "")
        payload = self._record(
            status="cancelled" if error_code == "cancelled" else "unavailable" if error_code in {"timeout", "provider_unavailable"} else "error",
            error_code=error_code,
            metadata=metadata,
            selected_provider=selected_provider,
            selected_model=selected_model,
            route_observation=route_observation,
            provider_supported_identity=False,
        )
        raise ProviderRouteError(payload)

    def _record(self, *, status, error_code, metadata=None, selected_provider="", selected_model="", route_observation="", provider_supported_identity=False, request_id=""):
        if metadata is not None:
            request_id = request_id or str(metadata.get("request_id") or "")
            if not selected_provider:
                selected_provider = str(metadata.get("observed_provider_name") or "")
            if not selected_model:
                selected_model = str(metadata.get("observed_model_name") or "")
        receipt = self._receipt(
            status=status,
            error_code=error_code,
            selected_provider=selected_provider,
            selected_model=selected_model,
            route_observation=route_observation,
            provider_supported_identity=provider_supported_identity,
            request_id=request_id,
        )
        self.task_receipts.append(receipt)
        self.session_retained = True
        return receipt

    def _receipt(self, *, status, error_code, selected_provider, selected_model, route_observation, provider_supported_identity, request_id, canary_identity="", live_canary=False):
        selected_router = INFERENCE_OWNER if selected_provider or selected_model or status == "available" else ""
        if status == "configured":
            selected_router = ""
        return {
            "kind": "task_receipt",
            "request_id": request_id,
            "session_id": self.session_id,
            "session_retained": True,
            "router": INFERENCE_OWNER,
            "requested_router": INFERENCE_OWNER,
            "selected_router": selected_router,
            "requested_provider": str(self.provider or ""),
            "selected_provider": selected_provider,
            "requested_model": str(self.model or ""),
            "selected_model": selected_model,
            "route_observation": route_observation,
            "provider_supported_identity": bool(provider_supported_identity),
            "status": status,
            "error_code": error_code,
            "error": _ERROR_TEXT.get(error_code, ""),
            "prompt_logged": False,
            "live_canary": bool(live_canary),
            "canary_identity": canary_identity,
            "remote_inference": self.remote_inference_disclosure(),
        }

    def _emit_progress(self, event: dict) -> None:
        safe = {key: value for key, value in event.items() if key in {"phase", "attempt", "max_attempts", "router", "status", "canary_identity"}}
        self.progress_events.append(safe)
        callback = self.progress_callback
        if callable(callback):
            callback(dict(safe))
        if os.getenv("COMPLAINT_GENERATOR_ROUTER_PROGRESS", "").strip() in {"1", "true", "yes"}:
            print("router_progress " + json.dumps(safe, sort_keys=True), flush=True)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            self._fail("cancelled", route_observation="cancelled")

    def _sleep_interruptible(self, seconds: float, deadline) -> None:
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            self._raise_if_cancelled()
            if deadline is not None and time.monotonic() >= deadline:
                self._fail("timeout", route_observation="timeout")
            time.sleep(min(0.05, end - time.monotonic()))

    def _compute_backoff_seconds(self, attempt: int) -> float:
        exp = max(0, attempt - 1)
        base = self.retry_backoff_base_s * (2 ** exp)
        base = min(base, self.retry_backoff_max_s)
        jitter = random.uniform(0.0, max(0.0, self.retry_jitter_s))
        return float(base + jitter)

    def _is_retryable_error(self, error: Exception) -> bool:
        if isinstance(error, ProviderRouteError):
            return error.payload.get("error_code") in {"provider_unavailable", "timeout"}
        message = str(error or '').lower()
        if message.startswith('llm_router_error:'):
            message = message.split(':', 1)[-1].strip()
        return any(s.lower() in message for s in self.retryable_error_substrings)

    def get_retry_stats(self):
        with self._stats_lock:
            return dict(self._retry_stats)


LLMRouter = LLMRouterBackend

TERMINAL_GROK_BACKEND_ID = "llm-router-grok-4.7"


def load_terminal_router_backend(config_path: str = "config.llm_router.json", backend_id: str = TERMINAL_GROK_BACKEND_ID):
    """Build the terminal Grok 4.7 backend from config without sending a prompt."""

    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    match = next((item for item in config.get("BACKENDS") or [] if item.get("id") == backend_id), None)
    if not isinstance(match, dict):
        raise KeyError(f"router backend {backend_id} is not configured")
    if match.get("type") != "llm_router":
        raise ValueError("terminal router backend must use llm_router")
    kwargs = dict(match)
    kwargs.pop("type", None)
    resolved_id = str(kwargs.pop("id"))
    provider = kwargs.pop("provider", None)
    model = kwargs.pop("model", None)
    return LLMRouterBackend(resolved_id, provider=provider, model=model, **kwargs)


def router_session_diagnostics_payload(config_path: str = "config.llm_router.json", backend_id: str = TERMINAL_GROK_BACKEND_ID):
    backend = load_terminal_router_backend(config_path, backend_id)
    return backend.sanitized_session_diagnostics()


def router_task_receipt_payload(config_path: str = "config.llm_router.json", backend_id: str = TERMINAL_GROK_BACKEND_ID):
    backend = load_terminal_router_backend(config_path, backend_id)
    return {"session_id": backend.session_id, "session_retained": True, "receipts": backend.task_receipt_snapshot()}
