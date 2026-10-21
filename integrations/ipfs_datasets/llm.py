from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from typing import Any, Dict, Mapping, Optional

from integrations.ipfs_accelerate.routers import (
	INFERENCE_OWNER,
	PINNED_GROK_CANARY_PROMPT,
	PINNED_GROK_MODEL,
	PINNED_GROK_PROVIDER,
	interpret_canary_dispatch,
	load_llm_symbols,
	load_observed_llm_symbols,
	normalize_accelerate_provider,
	pinned_grok47_canary_kwargs,
	pinned_grok47_dispatch_kwargs,
	unpinned_grok_route_reason,
	vetted_route_observation,
)
from .types import with_adapter_metadata


logger = logging.getLogger(__name__)


generate_text, get_last_generation_trace, _error = load_llm_symbols()
LLM_ROUTER_AVAILABLE = generate_text is not None
LLM_ROUTER_ERROR = _error


HF_ROUTER_DEFAULT_BASE_URL = "https://router.huggingface.co/v1"
HF_ARCH_ROUTER_MODEL = "katanemo/Arch-Router-1.5B"
HF_ROUTER_PROVIDER_ALIASES = {
	"hf_inference",
	"hf_router",
	"huggingface_inference",
	"huggingface_router",
}
_LLM_ROUTER_ENV_LOCK = threading.RLock()


def _coalesce_env(*names: str) -> str:
	for name in names:
		value = os.getenv(name, "").strip()
		if value:
			return value
	return ""


def _env_value(name: str, overrides: Optional[Mapping[str, str]] = None) -> str:
	if overrides is not None:
		value = str(overrides.get(name, "") or "").strip()
		if value:
			return value
	return os.getenv(name, "").strip()


def _resolve_hf_token(env_overrides: Optional[Mapping[str, str]] = None) -> str:
	token = (
		_env_value("IPFS_DATASETS_PY_HF_API_TOKEN", env_overrides)
		or _env_value("HUGGINGFACEHUB_API_TOKEN", env_overrides)
		or _env_value("HF_TOKEN", env_overrides)
		or _env_value("HUGGINGFACE_HUB_TOKEN", env_overrides)
		or _env_value("HUGGINGFACE_API_KEY", env_overrides)
		or _env_value("HUGGINGFACE_API_TOKEN", env_overrides)
		or _env_value("HF_API_TOKEN", env_overrides)
	)
	if token:
		return token

	try:
		from ipfs_datasets_py.mcp_server.secrets_vault import get_secrets_vault

		vault = get_secrets_vault()
		for name in (
			"IPFS_DATASETS_PY_HF_API_TOKEN",
			"HUGGINGFACEHUB_API_TOKEN",
			"HF_TOKEN",
			"HUGGINGFACE_HUB_TOKEN",
			"HUGGINGFACE_API_KEY",
			"HUGGINGFACE_API_TOKEN",
			"HF_API_TOKEN",
		):
			resolved = str(vault.get(name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# The vault is one of several supported credential sources, so its
		# failure must not prevent keyring or Hugging Face CLI credentials from
		# being used. Keep that fallback observable without logging secret values.
		logger.warning(
			"Could not resolve a Hugging Face token from the ipfs_datasets_py "
			"secrets vault; trying the keyring and Hugging Face CLI fallbacks",
			exc_info=True,
		)

	try:
		import keyring  # type: ignore

		for name in (
			"IPFS_DATASETS_PY_HF_API_TOKEN",
			"HUGGINGFACEHUB_API_TOKEN",
			"HF_TOKEN",
			"HUGGINGFACE_HUB_TOKEN",
			"HUGGINGFACE_API_KEY",
			"HUGGINGFACE_API_TOKEN",
			"HF_API_TOKEN",
		):
			resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# A broken or unconfigured keyring backend must not prevent the
		# Hugging Face client fallback below, but the degraded credential lookup
		# must remain observable to operators.
		logger.warning(
			"Hugging Face token lookup through keyring failed; "
			"falling back to the Hugging Face client token cache",
			exc_info=True,
		)

	try:
		hub = importlib.import_module("huggingface_hub")
		getter = getattr(hub, "get_token", None)
		resolved = getter() if callable(getter) else ""
		if resolved is not None and str(resolved).strip():
			return str(resolved).strip()
	except Exception:
		return ""
	return ""


def _resolve_openai_api_key(env_overrides: Optional[Mapping[str, str]] = None) -> str:
	token = (
		_env_value("OPENAI_API_KEY", env_overrides)
		or _env_value("OPENAI_KEY", env_overrides)
		or _env_value("OPENAI_TOKEN", env_overrides)
	)
	if token:
		return token

	try:
		from ipfs_datasets_py.mcp_server.secrets_vault import get_secrets_vault

		vault = get_secrets_vault()
		for name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
			resolved = str(vault.get(name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# The vault is optional and keyring/common-file lookup can still resolve
		# the key. Surface the degraded lookup without exposing credential values.
		logger.warning(
			"Could not resolve an OpenAI API key from the ipfs_datasets_py "
			"secrets vault; trying the keyring and common-file fallbacks",
			exc_info=True,
		)

	try:
		import keyring  # type: ignore

		for name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
			resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# Keyring is optional and common local configuration may still provide
		# the key. Preserve that fallback while making backend failures visible.
		logger.warning(
			"OpenAI API-key lookup through keyring failed; "
			"falling back to common local configuration files",
			exc_info=True,
		)

	try:
		engine_env = importlib.import_module("ipfs_datasets_py.utils.engine_env")
		getter = getattr(engine_env, "_openai_key_from_common_files", None)
		resolved = getter() if callable(getter) else ""
		if resolved is not None and str(resolved).strip():
			return str(resolved).strip()
	except Exception:
		return ""
	return ""


def _provider_preflight_error(
	*,
	effective_provider: str,
	metadata: Mapping[str, Any],
	env_overrides: Mapping[str, str],
) -> str:
	provider_key = str(effective_provider or "").strip().lower()
	requested_provider = str(metadata.get("requested_provider_name") or "").strip().lower()
	router_base_url = str(metadata.get("router_base_url") or "").strip().lower()

	if provider_key == "openrouter":
		is_hf_router_request = requested_provider in HF_ROUTER_PROVIDER_ALIASES or (
			requested_provider in {"hf", "huggingface"} and "huggingface.co" in router_base_url
		)
		if is_hf_router_request:
			hf_token = _resolve_hf_token(env_overrides)
			if not hf_token:
				return (
					"Hugging Face router unavailable: missing token. "
					"Set HF_TOKEN, HUGGINGFACE_HUB_TOKEN, HUGGINGFACE_API_KEY, or HF_API_TOKEN."
				)
		openrouter_key = _env_value("IPFS_DATASETS_PY_OPENROUTER_API_KEY", env_overrides) or _env_value("OPENROUTER_API_KEY")
		if not openrouter_key:
			return (
				"OpenRouter unavailable: missing API key. "
				"Set OPENROUTER_API_KEY or IPFS_DATASETS_PY_OPENROUTER_API_KEY."
			)

	if provider_key == "openai":
		openai_key = _resolve_openai_api_key(env_overrides)
		if not openai_key:
			return "OpenAI unavailable: missing API key. Set OPENAI_API_KEY, store one in the ipfs_datasets_py vault/keyring, or log in with a compatible local OpenAI CLI config."

	if provider_key == "anthropic":
		anthropic_key = _env_value("ANTHROPIC_API_KEY", env_overrides)
		if not anthropic_key:
			return "Anthropic unavailable: missing API key. Set ANTHROPIC_API_KEY."

	if provider_key in {"gemini", "gemini_cli", "gemini_py"}:
		gemini_key = (
			_env_value("GEMINI_API_KEY", env_overrides)
			or _env_value("GOOGLE_API_KEY", env_overrides)
		)
		if provider_key == "gemini" and not gemini_key:
			return "Gemini unavailable: missing API key. Set GEMINI_API_KEY or GOOGLE_API_KEY."

	if provider_key in {"codex", "codex_cli"} and shutil.which("codex") is None:
		return "Codex CLI unavailable: codex binary not found on PATH."

	if provider_key == PINNED_GROK_PROVIDER:
		model = str(metadata.get("effective_model_name") or "").strip()
		if model != PINNED_GROK_MODEL:
			return unpinned_grok_route_reason(provider_key, model) or (
				"Grok CLI unavailable: model_name must be exactly grok-4.7."
			)

	return ""


def grok_cli_binary_present() -> bool:
	"""PATH-only discovery. Operator home bins are not treated as available."""

	return shutil.which("grok") is not None


def grok_cli_auth_present() -> bool:
	"""Report whether auth is configured. Never read or return secret bytes."""

	for name in (
		"XAI_API_KEY",
		"ipfs_accelerate_py_XAI_API_KEY",
		"IPFS_ACCELERATE_PY_XAI_API_KEY",
		"IPFS_DATASETS_PY_XAI_API_KEY",
		"GROK_AUTH_PROVIDER_COMMAND",
	):
		if os.getenv(name, "").strip():
			return True
	candidates = []
	configured_home = os.getenv("GROK_HOME", "").strip()
	if configured_home:
		candidates.append(Path(configured_home).expanduser() / "auth.json")
	candidates.append(Path.home() / ".grok" / "auth.json")
	for path in candidates:
		try:
			if path.is_file() and path.stat().st_size > 0:
				return True
		except OSError:
			continue
	return False


def _new_request_id() -> str:
	return uuid.uuid4().hex


# One schema family for question proposals and extracted-fact candidates.
# Spans are exact UTF-8 byte offsets into the original source, not code points.
INTAKE_REQUEST_SCHEMA_VERSION = "intake_request_v1"
INTAKE_REQUEST_SCHEMA_NAME = "intake_request_v1"
INTAKE_OPERATIONS = frozenset({"propose_questions", "extract_facts"})
INTAKE_FACT_FIELDS = frozenset({"party", "date", "location", "act", "harm"})
INTAKE_MAX_QUESTIONS = 8
INTAKE_MAX_FACTS = 16
INTAKE_MAX_OUTPUT_BYTES = 262144
_INTAKE_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,128}\Z")
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}\Z")

INTAKE_REQUEST_OBJECT_SCHEMA: Dict[str, Any] = {
	"type": "object",
	"additionalProperties": False,
	"required": ["schema_version", "operation", "request_id", "questions", "facts"],
	"properties": {
		"schema_version": {"type": "string", "const": INTAKE_REQUEST_SCHEMA_VERSION},
		"operation": {"type": "string", "enum": ["propose_questions", "extract_facts"]},
		"request_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
		"questions": {
			"type": "array",
			"maxItems": INTAKE_MAX_QUESTIONS,
			"items": {
				"type": "object",
				"additionalProperties": False,
				"required": ["question_id", "prompt", "target_ref"],
				"properties": {
					"question_id": {"type": "string", "minLength": 1, "maxLength": 64},
					"prompt": {"type": "string", "minLength": 1, "maxLength": 500},
					"target_ref": {"type": "string", "minLength": 1, "maxLength": 128},
				},
			},
		},
		"facts": {
			"type": "array",
			"maxItems": INTAKE_MAX_FACTS,
			"items": {
				"type": "object",
				"additionalProperties": False,
				"required": ["field", "value", "source_start", "source_end", "target_ref"],
				"properties": {
					"field": {"type": "string", "enum": ["party", "date", "location", "act", "harm"]},
					"value": {"type": "string", "minLength": 1, "maxLength": 500},
					"source_start": {"type": "integer", "minimum": 0},
					"source_end": {"type": "integer", "minimum": 0},
					"target_ref": {"type": "string", "minLength": 1, "maxLength": 128},
				},
			},
		},
	},
}


class IntakeContractError(ValueError):
	"""Schema or source-span rejection. The message is a stable code, never model text."""

	def __init__(self, code: str = "malformed"):
		self.code = code if code in {"malformed", "identity", "span"} else "malformed"
		super().__init__(self.code)


def intake_request_response_format() -> Dict[str, Any]:
	"""Strict native response_format. Callers must not repair prose into this shape."""

	return {
		"type": "json_schema",
		"json_schema": {
			"name": INTAKE_REQUEST_SCHEMA_NAME,
			"strict": True,
			"schema": INTAKE_REQUEST_OBJECT_SCHEMA,
		},
	}


def _reject_duplicate_keys(items):
	parsed: Dict[str, Any] = {}
	for key, value in items:
		if key in parsed:
			raise IntakeContractError("malformed")
		parsed[key] = value
	return parsed


def _reject_nonfinite(_value):
	raise IntakeContractError("malformed")


def classify_router_failure(exc: BaseException) -> str:
	"""Map a provider failure to one stable kind. The kind never echoes the exception body."""

	name = type(exc).__name__.lower()
	if isinstance(exc, TimeoutError) or name in {"timeoutexpired", "timeouterror"}:
		return "timeout"
	if "cancel" in name:
		return "cancelled"
	text = str(exc).lower()
	if any(token in text for token in ("insufficient_quota", "quota exceeded", "quota_exhausted", "rate limit")):
		return "quota"
	if any(token in text for token in ("does not match the requested schema", "structured output", "malformed json", "duplicate fields")):
		return "malformed"
	return "unavailable"


def _host_validate_intake_tree(payload: Any, *, request_id: str, operation: str, source_text: str) -> Dict[str, Any]:
	if type(payload) is not dict:
		raise IntakeContractError("malformed")
	allowed = {"schema_version", "operation", "request_id", "questions", "facts"}
	if set(payload) != allowed:
		raise IntakeContractError("malformed")
	if payload.get("schema_version") != INTAKE_REQUEST_SCHEMA_VERSION:
		raise IntakeContractError("malformed")
	if payload.get("operation") not in INTAKE_OPERATIONS or payload.get("operation") != operation:
		raise IntakeContractError("identity")
	if type(payload.get("request_id")) is not str or payload.get("request_id") != request_id or _REQUEST_ID.fullmatch(request_id) is None:
		raise IntakeContractError("identity")
	questions = payload.get("questions")
	facts = payload.get("facts")
	if type(questions) is not list or type(facts) is not list:
		raise IntakeContractError("malformed")
	if len(questions) > INTAKE_MAX_QUESTIONS or len(facts) > INTAKE_MAX_FACTS:
		raise IntakeContractError("malformed")
	if operation == "propose_questions" and facts:
		raise IntakeContractError("malformed")
	if operation == "extract_facts" and questions:
		raise IntakeContractError("malformed")
	source = source_text.encode("utf-8")
	clean_questions = []
	for item in questions:
		if type(item) is not dict or set(item) != {"question_id", "prompt", "target_ref"}:
			raise IntakeContractError("malformed")
		question_id = item.get("question_id")
		prompt = item.get("prompt")
		target = item.get("target_ref")
		if type(question_id) is not str or type(prompt) is not str or type(target) is not str:
			raise IntakeContractError("malformed")
		if not (1 <= len(question_id) <= 64 and 1 <= len(prompt) <= 500 and _INTAKE_REF.fullmatch(target)):
			raise IntakeContractError("malformed")
		clean_questions.append({"question_id": question_id, "prompt": prompt, "target_ref": target})
	clean_facts = []
	for item in facts:
		if type(item) is not dict or set(item) != {"field", "value", "source_start", "source_end", "target_ref"}:
			raise IntakeContractError("span")
		field = item.get("field")
		value = item.get("value")
		start = item.get("source_start")
		end = item.get("source_end")
		target = item.get("target_ref")
		if field not in INTAKE_FACT_FIELDS or type(value) is not str or type(target) is not str:
			raise IntakeContractError("span")
		if type(start) is not int or type(end) is not int or isinstance(start, bool) or isinstance(end, bool):
			raise IntakeContractError("span")
		if not (1 <= len(value) <= 500 and _INTAKE_REF.fullmatch(target)):
			raise IntakeContractError("span")
		if start < 0 or end < start or end > len(source):
			raise IntakeContractError("span")
		try:
			excerpt = source[start:end].decode("utf-8")
		except UnicodeDecodeError:
			raise IntakeContractError("span") from None
		if excerpt != value:
			raise IntakeContractError("span")
		clean_facts.append({
			"field": field,
			"value": value,
			"source_start": start,
			"source_end": end,
			"target_ref": target,
		})
	return {
		"schema_version": INTAKE_REQUEST_SCHEMA_VERSION,
		"operation": operation,
		"request_id": request_id,
		"questions": clean_questions,
		"facts": clean_facts,
	}


def parse_intake_request(raw: str, *, request_id: str, operation: str, source_text: str) -> Dict[str, Any]:
	"""Validate one model payload. Fenced prose and regex extraction are not accepted."""

	if type(raw) is not str or len(raw.encode("utf-8")) > INTAKE_MAX_OUTPUT_BYTES:
		raise IntakeContractError("malformed")
	text = raw.strip()
	if not text or text[0] != "{":
		raise IntakeContractError("malformed")
	try:
		payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonfinite)
	except IntakeContractError:
		raise
	except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
		raise IntakeContractError("malformed") from None
	try:
		from ipfs_accelerate_py.cli_runtime.grok_structured_output import decode_response, validate_response_format

		_schema, _encoded, validator = validate_response_format(intake_request_response_format())
		decode_response(text, validator)
	except IntakeContractError:
		raise
	except ModuleNotFoundError:
		# Native jsonschema/referencing support is absent. Host field and span
		# checks still run; this does not accept unconstrained prose.
		pass
	except ImportError:
		pass
	except ValueError:
		raise IntakeContractError("malformed") from None
	except Exception:
		raise IntakeContractError("malformed") from None
	return _host_validate_intake_tree(payload, request_id=request_id, operation=operation, source_text=source_text)


def _pop_host_metadata(kwargs: Dict[str, Any]) -> Dict[str, Any]:
	"""Keep correlation and intake controls out of the provider allowlist."""

	request_id = kwargs.pop("request_id", None)
	if request_id is None:
		request_id = kwargs.pop("intake_request_id", None)
	else:
		kwargs.pop("intake_request_id", None)
	operation = kwargs.pop("intake_operation", None)
	source_text = kwargs.pop("intake_source_text", None)
	if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
		request_id = _new_request_id()
	if operation is not None and operation not in INTAKE_OPERATIONS:
		operation = None
	return {
		"request_id": request_id,
		"intake_operation": operation,
		"intake_source_text": source_text if type(source_text) is str else "",
	}


# Only literal first-party preflight messages may enter a public receipt.
# Partial prompt echoes and short credentials cannot be detected by length or
# comparison with the full prompt, so arbitrary exception text is never copied.
_PUBLIC_PREFLIGHT_ERRORS = frozenset({
	"Hugging Face router unavailable: missing token. Set HF_TOKEN, HUGGINGFACE_HUB_TOKEN, HUGGINGFACE_API_KEY, or HF_API_TOKEN.",
	"OpenRouter unavailable: missing API key. Set OPENROUTER_API_KEY or IPFS_DATASETS_PY_OPENROUTER_API_KEY.",
	"OpenAI unavailable: missing API key. Set OPENAI_API_KEY, store one in the ipfs_datasets_py vault/keyring, or log in with a compatible local OpenAI CLI config.",
	"Anthropic unavailable: missing API key. Set ANTHROPIC_API_KEY.",
	"Gemini unavailable: missing API key. Set GEMINI_API_KEY or GOOGLE_API_KEY.",
	"Codex CLI unavailable: codex binary not found on PATH.",
	"Grok CLI unavailable: model_name must be exactly grok-4.7.",
})


def _public_error(message: str, prompt: str) -> str:
	"""Preserve actionable literal diagnostics; drop all dynamic error bodies."""

	return message if type(message) is str and message in _PUBLIC_PREFLIGHT_ERRORS else "provider_exception"


def _apply_pinned_grok_options(provider: str, call_options: Dict[str, Any]) -> None:
	if str(provider or "").strip() != PINNED_GROK_PROVIDER:
		return
	call_options.update(
		{
			"allow_local_fallback": False,
			"allow_cross_provider_fallback": False,
		}
	)


def _redacted_router_trace(trace: Any, *, request_id: str, requested_provider: str, requested_model: str) -> Dict[str, Any]:
	"""Copy route identity only. Prompt, credentials, and raw errors stay out."""

	fields = vetted_route_observation(
		trace if isinstance(trace, Mapping) else None,
		requested_provider=requested_provider,
		requested_model=requested_model,
	)
	version = ""
	if isinstance(trace, Mapping):
		for key in ("router_version", "model_version", "effective_model_version"):
			value = trace.get(key)
			if type(value) is str and value.strip() and len(value) <= 64 and " " not in value:
				version = value.strip()
				break
	fields["request_id"] = request_id
	fields["router_version"] = version
	fields["configured_provider_name"] = requested_provider
	fields["configured_model_name"] = requested_model
	fields["inference_owner"] = INFERENCE_OWNER
	fields["prompt_logged"] = False
	return fields


def _route_receipt(
	*,
	requested_provider: str,
	requested_model: str,
	observe: bool,
	request_id: str = "",
) -> Dict[str, Any]:
	trace: Any = None
	if observe and callable(get_last_generation_trace):
		try:
			trace = get_last_generation_trace()
		except Exception:
			trace = None
	if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
		request_id = _new_request_id()
	return _redacted_router_trace(
		trace,
		request_id=request_id,
		requested_provider=requested_provider,
		requested_model=requested_model,
	)


def _pop_first_string(options: Dict[str, Any], *names: str) -> str:
	for name in names:
		value = options.pop(name, None)
		if value is None:
			continue
		text = str(value).strip()
		if text:
			return text
	return ""


def _normalize_headers(value: Any) -> Dict[str, str]:
	if isinstance(value, Mapping):
		return {
			str(key).strip(): str(item).strip()
			for key, item in value.items()
			if str(key).strip() and str(item).strip()
		}
	return {}


def _coerce_bool(value: Any) -> bool:
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _slugify_route_name(value: str) -> str:
	text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
	return text.strip("_") or "route"


def _normalize_arch_router_routes(value: Any) -> list[Dict[str, str]]:
	routes: list[Dict[str, str]] = []
	if isinstance(value, Mapping):
		for name, route_value in value.items():
			if isinstance(route_value, Mapping):
				model = str(route_value.get("model") or route_value.get("target_model") or "").strip()
				description = str(route_value.get("description") or route_value.get("prompt") or "").strip()
			else:
				model = str(route_value or "").strip()
				description = ""
			if model:
				routes.append({
					"name": _slugify_route_name(str(name)),
					"model": model,
					"description": description or f"Use when the prompt is best handled by {model}.",
				})
		return routes

	if isinstance(value, (list, tuple)):
		for index, item in enumerate(value, start=1):
			if isinstance(item, Mapping):
				model = str(item.get("model") or item.get("target_model") or "").strip()
				name = str(item.get("name") or item.get("route") or model or f"route_{index}").strip()
				description = str(item.get("description") or item.get("prompt") or "").strip()
			elif item is None:
				continue
			else:
				model = str(item).strip()
				name = model
				description = ""
			if model:
				routes.append({
					"name": _slugify_route_name(name),
					"model": model,
					"description": description or f"Use when the prompt is best handled by {model}.",
				})
	return routes


def _extract_arch_router_config(options: Dict[str, Any]) -> Dict[str, Any]:
	nested = options.pop("arch_router", None)
	nested_config = dict(nested) if isinstance(nested, Mapping) else {}
	routes_value = (
		nested_config.pop("routes", None)
		or nested_config.pop("candidates", None)
		or options.pop("arch_router_routes", None)
		or options.pop("routing_candidates", None)
		or options.pop("candidate_models", None)
	)
	routes = _normalize_arch_router_routes(routes_value)
	enabled = _coerce_bool(
		nested_config.pop("enabled", None)
		or nested_config.pop("auto", None)
		or options.pop("arch_router_enabled", None)
		or options.pop("auto_route_model", None)
		or options.pop("auto_model_routing", None)
	)
	if routes and not enabled:
		enabled = True
	return {
		"enabled": enabled,
		"model": str(
			nested_config.pop("model", None)
			or options.pop("arch_router_model", None)
			or _coalesce_env("HF_ARCH_ROUTER_MODEL", "LLM_ROUTER_ARCH_MODEL")
			or HF_ARCH_ROUTER_MODEL
		).strip(),
		"routes": routes,
		"context": str(
			nested_config.pop("context", None)
			or options.pop("arch_router_context", None)
			or ""
		).strip(),
	}


def _strip_code_fences(text: str) -> str:
	stripped = str(text or "").strip()
	if stripped.startswith("```"):
		parts = stripped.splitlines()
		if parts:
			parts = parts[1:]
		while parts and parts[-1].strip().startswith("```"):
			parts = parts[:-1]
		stripped = "\n".join(parts).strip()
	return stripped


def _parse_arch_router_route(text: str) -> str:
	stripped = _strip_code_fences(text)
	try:
		payload = json.loads(stripped)
	except json.JSONDecodeError:
		# Router models do not always honor the JSON-only instruction. Preserve
		# the tolerant regex/plain-text fallbacks only for malformed JSON; parser
		# defects and unexpected runtime failures must remain visible to callers.
		payload = None
	if isinstance(payload, Mapping):
		return str(payload.get("route") or payload.get("name") or "").strip()
	match = re.search(r'"route"\s*:\s*"([^"]+)"', stripped)
	if match:
		return match.group(1).strip()
	return stripped.strip().strip('"')


def _build_arch_router_prompt(prompt: str, routes: list[Dict[str, str]], context: str = "") -> str:
	route_lines = []
	for route in routes:
		route_lines.append(
			"<route>\n"
			f"<name>{route['name']}</name>\n"
			f"<model>{route['model']}</model>\n"
			f"<description>{route['description']}</description>\n"
			"</route>"
		)
	context_block = f"<context>{context}</context>\n" if context else ""
	return (
		"You are a routing model. Select the single best route for the user request. "
		"Return JSON only in the form {\"route\": \"route_name\"}.\n"
		"<routes>\n"
		+ "\n".join(route_lines)
		+ "\n</routes>\n"
		+ context_block
		+ "<user_request>\n"
		+ prompt.strip()
		+ "\n</user_request>"
	)


def _select_huggingface_arch_route(
	prompt: str,
	*,
	base_url: str,
	api_key: str,
	referer: str,
	app_title: str,
	arch_router_config: Dict[str, Any],
	fallback_model_name: Optional[str],
) -> Dict[str, str]:
	routes = list(arch_router_config.get("routes") or [])
	if not arch_router_config.get("enabled") or not routes or generate_text is None:
		return {}

	routing_prompt = _build_arch_router_prompt(prompt, routes, context=str(arch_router_config.get("context") or ""))
	routing_model = str(arch_router_config.get("model") or HF_ARCH_ROUTER_MODEL).strip() or HF_ARCH_ROUTER_MODEL
	env_overrides = {
		"IPFS_DATASETS_PY_OPENROUTER_BASE_URL": base_url.rstrip("/"),
	}
	if api_key:
		env_overrides["IPFS_DATASETS_PY_OPENROUTER_API_KEY"] = api_key
	if referer:
		env_overrides["OPENROUTER_HTTP_REFERER"] = referer
	if app_title:
		env_overrides["OPENROUTER_APP_TITLE"] = app_title

	with _temporary_env(env_overrides):
		raw_response = generate_text(
			prompt=routing_prompt,
			provider="openrouter",
			model_name=routing_model,
			temperature=0,
		)

	selected_route = _slugify_route_name(_parse_arch_router_route(raw_response))
	for route in routes:
		if route["name"] == selected_route:
			return {
				"arch_router_selected_route": selected_route,
				"arch_router_selected_model": route["model"],
				"arch_router_model_name": routing_model,
				"arch_router_status": "selected",
			}

	return {
		"arch_router_selected_route": selected_route,
		"arch_router_selected_model": str(fallback_model_name or ""),
		"arch_router_model_name": routing_model,
		"arch_router_status": "fallback",
	}


def _is_huggingface_router_request(provider: Optional[str], options: Dict[str, Any]) -> bool:
	provider_key = str(provider or "").strip().lower()
	if provider_key in HF_ROUTER_PROVIDER_ALIASES:
		return True
	base_url = str(
		options.get("base_url")
		or options.get("api_base")
		or options.get("api_base_url")
		or options.get("router_base_url")
		or options.get("llm_router_base_url")
		or ""
	).strip().lower()
	if "huggingface.co" in base_url:
		return True
	return provider_key in {"hf", "huggingface"} and bool(base_url)


def _build_huggingface_router_request(
	prompt: str,
	provider: Optional[str],
	model_name: Optional[str],
	options: Dict[str, Any],
) -> tuple[str, Optional[str], Dict[str, Any], Dict[str, str], Dict[str, Any]]:
	call_options = dict(options)
	headers = _normalize_headers(call_options.pop("headers", None))
	arch_router_config = _extract_arch_router_config(call_options)
	authorization = headers.pop("Authorization", "")
	bearer_token = ""
	if authorization.lower().startswith("bearer "):
		bearer_token = authorization[7:].strip()

	base_url = _pop_first_string(
		call_options,
		"base_url",
		"api_base",
		"api_base_url",
		"router_base_url",
		"llm_router_base_url",
	) or _coalesce_env(
		"HUGGINGFACE_LLM_ROUTER_BASE_URL",
		"HF_LLM_ROUTER_BASE_URL",
		"LLM_ROUTER_ARCH_BASE_URL",
	) or HF_ROUTER_DEFAULT_BASE_URL

	api_key = _pop_first_string(call_options, "api_key", "token", "access_token") or bearer_token or _resolve_hf_token()
	referer = _pop_first_string(call_options, "http_referer", "referer") or headers.pop("HTTP-Referer", "") or headers.pop("Referer", "")
	app_title = _pop_first_string(call_options, "app_title") or headers.pop("X-Title", "")
	bill_to = _pop_first_string(call_options, "bill_to", "hf_bill_to") or headers.pop("X-HF-Bill-To", "") or _coalesce_env(
		"IPFS_DATASETS_PY_HF_BILL_TO",
		"HUGGINGFACE_BILL_TO",
		"HF_BILL_TO",
		"HF_ORGANIZATION",
		"HUGGINGFACE_ORG",
		"OPENROUTER_HF_BILL_TO",
	)

	effective_model_name = model_name or _pop_first_string(call_options, "route_model", "fallback_model") or _coalesce_env(
		"LLM_ROUTER_FALLBACK_MODEL",
		"IPFS_DATASETS_PY_OPENROUTER_MODEL",
		"IPFS_DATASETS_PY_LLM_MODEL",
	) or None
	try:
		route_selection = _select_huggingface_arch_route(
			prompt,
			base_url=base_url,
			api_key=api_key,
			referer=referer,
			app_title=app_title,
			arch_router_config=arch_router_config,
			fallback_model_name=effective_model_name,
		)
	except Exception as exc:
		route_selection = {
			"arch_router_status": "fallback_error",
			"arch_router_selected_route": "",
			"arch_router_selected_model": str(effective_model_name or ""),
			"arch_router_model_name": str(arch_router_config.get("model") or HF_ARCH_ROUTER_MODEL),
			"arch_router_error": str(exc),
		}
	selected_model_name = str(route_selection.get("arch_router_selected_model") or "").strip()
	if selected_model_name:
		effective_model_name = selected_model_name

	env_overrides = {
		"IPFS_DATASETS_PY_OPENROUTER_BASE_URL": base_url.rstrip("/"),
	}
	if api_key:
		env_overrides["IPFS_DATASETS_PY_OPENROUTER_API_KEY"] = api_key
	if effective_model_name:
		env_overrides["IPFS_DATASETS_PY_OPENROUTER_MODEL"] = str(effective_model_name)
	if referer:
		env_overrides["OPENROUTER_HTTP_REFERER"] = referer
	if app_title:
		env_overrides["OPENROUTER_APP_TITLE"] = app_title
	if bill_to:
		env_overrides["OPENROUTER_HF_BILL_TO"] = bill_to

	metadata = {
		"requested_provider_name": provider or "",
		"effective_provider_name": "openrouter",
		"effective_model_name": str(effective_model_name or ""),
		"router_base_url": base_url.rstrip("/"),
		"hf_bill_to": bill_to,
		**route_selection,
	}
	return "openrouter", effective_model_name, call_options, env_overrides, metadata


def _prepare_generate_text_call(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> tuple[str, Optional[str], Dict[str, Any], Dict[str, str], Dict[str, Any]]:
	call_options = dict(kwargs)
	if _is_huggingface_router_request(provider, call_options):
		return _build_huggingface_router_request(prompt, provider, model_name, call_options)
	mapped_provider = normalize_accelerate_provider(provider)
	metadata = {
		"requested_provider_name": provider or "",
		"effective_provider_name": mapped_provider or "",
		"effective_model_name": str(model_name or ""),
		"router_base_url": "",
	}
	_apply_pinned_grok_options(str(mapped_provider or ""), call_options)
	return str(mapped_provider or ""), model_name, call_options, {}, metadata


@contextmanager
def _temporary_env(overrides: Dict[str, str]):
	if not overrides:
		yield
		return
	with _LLM_ROUTER_ENV_LOCK:
		previous = {key: os.environ.get(key) for key in overrides}
		try:
			for key, value in overrides.items():
				os.environ[key] = str(value)
			yield
		finally:
			for key, value in previous.items():
				if value is None:
					os.environ.pop(key, None)
				else:
					os.environ[key] = value


def generate_text_via_router(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> str:
	host_meta = _pop_host_metadata(kwargs)
	if host_meta["intake_operation"] is not None:
		kwargs["response_format"] = intake_request_response_format()
	privacy_context = kwargs.pop("complaint_privacy_context", None)
	privacy_block = _privacy_context_block_reason(
		privacy_context,
		provider=provider,
		model_name=model_name,
		options=kwargs,
	)
	if privacy_block:
		raise RuntimeError(privacy_block)
	if generate_text is None:
		raise RuntimeError("private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable")
	if privacy_context is not None:
		provider, model_name = PRIVACY_GROK_PROVIDER, PRIVACY_GROK_MODEL
		kwargs = _private_generation_options(kwargs)
	route_block = unpinned_grok_route_reason(provider, model_name)
	if route_block:
		raise RuntimeError("private_generation_preflight_unavailable" if privacy_context is not None else route_block)
	effective_provider, effective_model_name, call_options, env_overrides, _ = _prepare_generate_text_call(
		prompt,
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	preflight_error = _provider_preflight_error(
		effective_provider=effective_provider,
		metadata=_,
		env_overrides=env_overrides,
	)
	if preflight_error:
		if privacy_context is not None:
			raise RuntimeError("private_generation_preflight_unavailable")
		raise RuntimeError(_public_error(preflight_error, prompt))
	try:
		with _temporary_env(env_overrides):
			return generate_text(
				prompt=prompt,
				provider=effective_provider or None,
				model_name=effective_model_name,
				**call_options,
			)
	except Exception:
		if privacy_context is not None:
			raise RuntimeError("private_generation_failed") from None
		if effective_provider == PINNED_GROK_PROVIDER:
			raise RuntimeError("provider_exception") from None
		raise


def generate_text_with_metadata(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> Dict[str, Any]:
	host_meta = _pop_host_metadata(kwargs)
	request_id = host_meta["request_id"]
	intake_operation = host_meta["intake_operation"]
	intake_source_text = host_meta["intake_source_text"]
	if intake_operation is not None:
		kwargs["response_format"] = intake_request_response_format()
		kwargs.setdefault("max_tokens", 1024)
	privacy_context = kwargs.pop("complaint_privacy_context", None)
	privacy_block = _privacy_context_block_reason(
		privacy_context,
		provider=provider,
		model_name=model_name,
		options=kwargs,
	)
	if privacy_block:
		return with_adapter_metadata(
			{"status": "error", "text": "", "provider_name": provider or "",
			 "model_name": model_name or "", "error": privacy_block,
			 "privacy_decision": "denied", "dispatch": "none"},
			operation="generate_text", backend_available=generate_text is not None,
			implementation_status="available" if generate_text is not None else "unavailable",
		)
	if generate_text is None:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				"resumable": True,
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "unavailable",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=False,
			degraded_reason="private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable",
			implementation_status="unavailable",
		)

	if privacy_context is not None:
		provider, model_name = PRIVACY_GROK_PROVIDER, PRIVACY_GROK_MODEL
		kwargs = _private_generation_options(kwargs)
	route_block = unpinned_grok_route_reason(provider, model_name)
	if route_block:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				"requested_provider_name": provider or "",
				"requested_model_name": model_name or "",
				"error": "private_generation_preflight_unavailable" if privacy_context is not None else route_block,
				"availability_hint": "private_generation_preflight_unavailable" if privacy_context is not None else route_block,
				"resumable": True,
				"dispatch": "none",
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "unavailable",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)
	effective_provider, effective_model_name, call_options, env_overrides, metadata = _prepare_generate_text_call(
		prompt,
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	preflight_error = _provider_preflight_error(
		effective_provider=effective_provider,
		metadata=metadata,
		env_overrides=env_overrides,
	)
	if preflight_error:
		private_preflight = privacy_context is not None
		grok_preflight = str(effective_provider or "") == PINNED_GROK_PROVIDER
		public_preflight = "private_generation_preflight_unavailable" if private_preflight else _public_error(preflight_error, prompt)
		return with_adapter_metadata(
			{
				"status": "error" if private_preflight or not grok_preflight else "unavailable",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				**metadata,
				"error": public_preflight,
				"availability_hint": public_preflight,
				"resumable": True,
				"dispatch": "none",
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "unavailable",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)

	try:
		with _temporary_env(env_overrides):
			text = generate_text(
				prompt=prompt,
				provider=effective_provider or None,
				model_name=effective_model_name,
				**call_options,
			)
	except Exception as exc:
		private_failure = privacy_context is not None
		grok_failure = str(effective_provider or "") == PINNED_GROK_PROVIDER
		kind = classify_router_failure(exc)
		if private_failure:
			public_error = "private_generation_failed"
			status = "error" if kind == "unavailable" else kind
		elif grok_failure and kind == "unavailable":
			public_error = "provider_exception"
			status = "unavailable"
		elif grok_failure:
			public_error = kind
			status = kind
		else:
			public_error = "provider_exception"
			status = "error" if kind == "unavailable" else kind
		receipt = _route_receipt(
			requested_provider=str(metadata.get("effective_provider_name") or effective_provider or ""),
			requested_model=str(metadata.get("effective_model_name") or effective_model_name or ""),
			observe=True,
			request_id=request_id,
		)
		receipt.pop("requested_provider_name", None)
		receipt.pop("requested_model_name", None)
		return with_adapter_metadata(
			{
				"status": status,
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				**metadata,
				**receipt,
				"error": public_error,
				"availability_hint": public_error,
				"failure_kind": kind,
				"resumable": True,
				"dispatch": "attempted",
				"live_canary": False,
				"intake_complete": False,
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)

	if type(text) is not str or len(text.encode("utf-8")) > INTAKE_MAX_OUTPUT_BYTES:
		text = ""
		oversize = True
	else:
		oversize = False
	parsed = None
	if intake_operation is not None:
		try:
			parsed = None if oversize else parse_intake_request(
				text,
				request_id=request_id,
				operation=intake_operation,
				source_text=intake_source_text,
			)
		except IntakeContractError:
			parsed = None
		if parsed is None:
			receipt = _route_receipt(
				requested_provider=str(metadata.get("effective_provider_name") or effective_provider or ""),
				requested_model=str(metadata.get("effective_model_name") or effective_model_name or ""),
				observe=True,
				request_id=request_id,
			)
			receipt.pop("requested_provider_name", None)
			receipt.pop("requested_model_name", None)
			return with_adapter_metadata(
				{
					"status": "malformed",
					"text": "",
					"provider_name": provider or "",
					"model_name": model_name or "",
					**metadata,
					**receipt,
					"error": "malformed",
					"failure_kind": "malformed",
					"resumable": True,
					"dispatch": "attempted",
					"live_canary": False,
					"intake_complete": False,
					"prompt_logged": False,
				},
				operation="generate_text",
				backend_available=True,
				implementation_status="available",
			)
		text = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
	elif oversize:
		text = ""

	receipt = _route_receipt(
		requested_provider=str(metadata.get("effective_provider_name") or effective_provider or ""),
		requested_model=str(metadata.get("effective_model_name") or effective_model_name or ""),
		observe=True,
		request_id=request_id,
	)
	receipt.pop("requested_provider_name", None)
	receipt.pop("requested_model_name", None)
	successful_empty = bool(parsed is not None and not parsed["questions"] and not parsed["facts"])
	return with_adapter_metadata(
		{
			"status": "available",
			"text": text,
			"provider_name": provider or "",
			"model_name": model_name or "",
			**metadata,
			**receipt,
			"resumable": False,
			"failure_kind": "",
			"intake_complete": False,
			"successful_empty": successful_empty,
			"prompt_logged": False,
		},
		operation="generate_text",
		backend_available=True,
		implementation_status="available",
	)


def llm_router_status(
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	prompt: str = "",
	perform_probe: bool = False,
	**kwargs: Any,
) -> Dict[str, Any]:
	privacy_context = kwargs.pop("complaint_privacy_context", None)
	if generate_text is None:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"configured_provider_name": provider or "",
				"configured_model_name": model_name or "",
				"effective_provider_name": "",
				"effective_model_name": "",
				"probe_performed": False,
				"dispatch": "none",
				"static_capability_only": True,
				"error": "private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable",
			},
			operation="llm_router_status",
			backend_available=False,
			degraded_reason="private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable",
			implementation_status="unavailable",
		)

	if not perform_probe:
		return with_adapter_metadata(
			{
				"status": "available",
				"configured_provider_name": provider or "",
				"configured_model_name": model_name or "",
				"effective_provider_name": "",
				"effective_model_name": "",
				"probe_performed": False,
				"dispatch": "none",
				"static_capability_only": True,
				"error": "",
			},
			operation="llm_router_status",
			backend_available=True,
			implementation_status="available",
		)

	if privacy_context is None:
		privacy_block = PRIVACY_DENIAL_CLOUD_DISABLED
	else:
		privacy_block = _privacy_context_block_reason(
			privacy_context,
			provider=provider,
			model_name=model_name,
			options=kwargs,
		)
	if privacy_block:
		return with_adapter_metadata(
			{
				"status": "error",
				"configured_provider_name": provider or "",
				"configured_model_name": model_name or "",
				"effective_provider_name": "",
				"effective_model_name": "",
				"probe_performed": False,
				"dispatch": "none",
				"static_capability_only": False,
				"privacy_decision": "denied",
				"error": privacy_block,
			},
			operation="llm_router_status",
			backend_available=False,
			degraded_reason=privacy_block,
			implementation_status="available",
		)

	provider, model_name = PRIVACY_GROK_PROVIDER, PRIVACY_GROK_MODEL
	kwargs = _private_generation_options(kwargs)
	effective_provider, effective_model_name, _, env_overrides, metadata = _prepare_generate_text_call(
		prompt or "HACC llm_router health check",
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	preflight_error = _provider_preflight_error(
		effective_provider=effective_provider,
		metadata=metadata,
		env_overrides=env_overrides,
	)
	payload: Dict[str, Any] = {
		"status": "available" if not preflight_error else "degraded",
		"configured_provider_name": provider or "",
		"configured_model_name": model_name or "",
		"effective_provider_name": effective_provider or "",
		"effective_model_name": effective_model_name or "",
		"probe_performed": False,
		"error": "private_generation_preflight_unavailable" if preflight_error else "",
		**metadata,
	}

	if perform_probe:
		probe_prompt = prompt or "Return a one-line router health confirmation for the HACC complaint workflow."
		probe_kwargs = dict(kwargs)
		if privacy_context is not None:
			probe_kwargs["complaint_privacy_context"] = privacy_context
		probe_payload = generate_text_with_metadata(
			probe_prompt,
			provider=provider,
			model_name=model_name,
			**probe_kwargs,
		)
		payload["probe_performed"] = True
		payload["probe_status"] = probe_payload.get("status")
		payload["probe_error"] = probe_payload.get("error", "")
		payload["probe_text_preview"] = str(probe_payload.get("text") or "")[:160]
		if probe_payload.get("status") != "available":
			payload["status"] = "error"
			payload["error"] = str(probe_payload.get("error") or preflight_error or "")

	return with_adapter_metadata(
		payload,
		operation="llm_router_status",
		backend_available=payload["status"] == "available",
		degraded_reason=payload.get("error") or None,
		implementation_status="available" if payload["status"] != "unavailable" else "unavailable",
	)


def grok47_route_capability(
	*,
	include_canary: bool = False,
	canary_transport: Any = None,
) -> Dict[str, Any]:
	"""Inspect configuration, or explicitly dispatch one synthetic canary.

	Static presence is configuration evidence, never a selected route. An
	injected transport cannot attest a live call. The pinned native router's
	public string result and selection trace do not expose invocation-bound
	wire-model evidence; only the optional native observation API can verify it.
	"""

	if type(include_canary) is not bool:
		raise ValueError("include_canary must be an explicit boolean")
	if canary_transport is not None and not callable(canary_transport):
		raise ValueError("canary_transport must be callable")
	router_ready = callable(generate_text)
	binary_ready = grok_cli_binary_present()
	auth_ready = grok_cli_auth_present()
	gaps = []
	if not router_ready:
		gaps.append("llm_router symbol is unavailable. The pinned route was not dispatched.")
	if not binary_ready:
		gaps.append(
			"Grok CLI unavailable: grok binary not found on PATH. "
			"No fallback provider was contacted."
		)
	if not auth_ready:
		gaps.append(
			"Grok CLI unavailable: missing authentication. "
			"Set XAI_API_KEY or sign in so the active HOME has a non-empty Grok CLI auth file. "
			"No fallback provider was contacted."
		)
	payload: Dict[str, Any] = {
		"inference_owner": INFERENCE_OWNER,
		"requested_provider_name": PINNED_GROK_PROVIDER,
		"requested_model_name": PINNED_GROK_MODEL,
		"selected_provider_name": "",
		"selected_model_name": "",
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
		"router_symbol_available": router_ready,
		"binary_available": binary_ready,
		"auth_present": auth_ready,
		"model_pinned": True,
		"static_capability_only": True,
		"probe_performed": False,
		"canary_enabled": include_canary,
		"live_canary": False,
		"provider_reported_model": "",
		"response_cache_hit": False,
		"canary_token_matched": False,
		"dispatch": "none",
		"request_id": _new_request_id(),
		"text": "",
		"status": "unavailable" if gaps else "available",
		"error": " ".join(gaps),
		"resumable": bool(gaps),
		"route_observation": "unverified",
		"route_evidence_class": "absent",
	}
	if gaps or not include_canary:
		return with_adapter_metadata(
			payload,
			operation="grok47_route_capability",
			backend_available=not gaps and router_ready,
			degraded_reason=payload["error"] or None,
			implementation_status="available" if router_ready else "unavailable",
		)

	injected = canary_transport is not None
	observed_generate, result_type, observation_type = (None, None, None) if injected else load_observed_llm_symbols()
	observed_api = callable(observed_generate) and isinstance(result_type, type) and isinstance(observation_type, type)
	transport = canary_transport if injected else (observed_generate if observed_api else generate_text)
	payload["static_capability_only"] = False
	payload["probe_performed"] = True
	payload["canary_transport"] = "injected" if injected else "llm_router"
	try:
		canary_kwargs = pinned_grok47_canary_kwargs()
		if observed_api:
			canary_kwargs["observation_request_id"] = payload["request_id"]
		result = transport(prompt=PINNED_GROK_CANARY_PROMPT, **canary_kwargs)
	except Exception:
		payload.update({"status": "unavailable", "error": "provider_exception",
			"availability_hint": "provider_exception", "resumable": True, "dispatch": "attempted"})
		return with_adapter_metadata(payload, operation="grok47_route_capability",
			backend_available=True, degraded_reason="provider_exception", implementation_status="available")

	payload.update(interpret_canary_dispatch(result))
	observed_text = result.get("text") if isinstance(result, Mapping) else result
	observation = None
	if observed_api and type(result) is result_type and type(result.observation) is observation_type:
		candidate = result.observation
		if (candidate.request_id == payload["request_id"]
				and type(candidate.invocation_id) is str and re.fullmatch(r"[0-9a-f]{32}", candidate.invocation_id)
				and type(candidate.native_dispatch_count) is int and candidate.native_dispatch_count == 1
				and candidate.invocation_scope == "current_call"
				and candidate.observation_only is True and candidate.raw_provider_data_exported is False
				and candidate.schema == "native-grok-invocation-observation@1"
				and type(candidate.process_returncode) is int and candidate.process_returncode == 0
				and candidate.stream_complete is True
				and candidate.selected_provider_name == PINNED_GROK_PROVIDER
				and candidate.selected_model_name == PINNED_GROK_MODEL):
			observation = candidate
			observed_text = result.text
	payload["canary_token_matched"] = isinstance(observed_text, str) and observed_text.strip() == PINNED_GROK_CANARY_PROMPT
	if observation is not None:
		payload["native_invocation_id"] = observation.invocation_id
		payload["selected_provider_name"] = observation.selected_provider_name
		payload["selected_model_name"] = observation.selected_model_name
		payload["route_observation"] = "verified"
		payload["route_evidence_class"] = "native_invocation"
		if (observation.wire_model_observed is True
				and observation.evidence_class == "native_final_end_model_usage"
				and type(observation.provider_reported_model) is str
				and re.fullmatch(r"grok-[0-9]{1,2}(?:\.[0-9]{1,2}){0,2}(?:-build)?", observation.provider_reported_model)):
			payload["provider_reported_model"] = observation.provider_reported_model
			# The requested route remains exactly grok-4.7. Grok's observed native
			# build label is retained verbatim and accepted only by this explicit set.
			model_matches = observation.provider_reported_model in {PINNED_GROK_MODEL, "grok-4.7-build"}
			if model_matches and payload["canary_token_matched"]:
				payload.update({"live_canary": True, "status": "available", "dispatch": "canary",
					"error": "", "resumable": False})
			else:
				payload.update({"status": "unavailable", "dispatch": "canary_rejected",
					"error": "canary_model_or_token_mismatch", "resumable": True})
	if payload["dispatch"] == "none":
		payload.update({
			"dispatch": "canary_unverified", "status": "unverified",
			"error": "Grok canary lacks invocation-bound wire-model evidence from the native router. Injected or cached results and router selection cannot verify a live canary.",
			"resumable": True,
		})
	return with_adapter_metadata(payload, operation="grok47_route_capability",
		backend_available=payload["status"] == "available", degraded_reason=payload["error"] or None,
		implementation_status="available")


# Versioned complaint privacy contract. The router stays independent of the
# application package; workspace code imports these helpers lazily.
PRIVACY_POLICY_CONTRACT = "complaint_privacy_policy"
PRIVACY_POLICY_VERSION = "1"
PRIVACY_CONTEXT_CONTRACT = "complaint_privacy_context"
PRIVACY_PROCESSING_LOCAL = "local_private"
PRIVACY_PROCESSING_GROK = "grok_cloud"
PRIVACY_GROK_PROVIDER = "grok_cli"
PRIVACY_GROK_MODEL = "grok-4.7"
PRIVACY_SCOPE_USER_CASE = "user_case"
PRIVACY_AT_REST_PROTECTION = "plaintext_pending"
PRIVACY_DENIAL_CLOUD_DISABLED = "privacy_denied:cloud_processing_disabled"
PRIVACY_DENIAL_SCOPE = "privacy_denied:grok_scope_mismatch"
PRIVACY_DENIAL_CASE = "privacy_denied:case_binding"
PRIVACY_DENIAL_VERSION = "privacy_denied:version"
PRIVACY_DENIAL_SCOPE_FIELD = "privacy_denied:scope"
PRIVACY_DENIAL_MALFORMED = "privacy_denied:malformed_consent"

PRIVATE_DATA_CLASSES: tuple[tuple[str, str], ...] = (
	("raw_intake", "Raw intake answers and intake history for one user and case."),
	("attachments", "Attachment names and bytes supplied for the case."),
	("fact_kg", "Claim-specific fact knowledge graph."),
	("claim_dependency_evaluations", "Claim-specific dependency and element evaluations."),
	("annotations", "Document and workspace annotations tied to the case."),
	("drafts_proofs", "Drafts, proof runs, and case theorem exports."),
	("embeddings", "Embeddings derived from private case text."),
	("exports", "Filing exports produced from the case."),
	("logs", "Logs that can quote private case content."),
	("caches", "Caches derived from private case content."),
	("temporary_files", "Temporary files created while processing the case."),
	("backups", "Backups of private session and case state."),
)
PUBLIC_LEGAL_SOURCE_CLASS = (
	"public_legal_source_graph",
	"Published legal sources. Distinct from the private claim fact graph.",
)
_PRIVATE_CLASS_IDS = {item[0] for item in PRIVATE_DATA_CLASSES}
_KNOWN_DATA_CLASSES = _PRIVATE_CLASS_IDS | {PUBLIC_LEGAL_SOURCE_CLASS[0]}
_AMBIENT_PROVIDER_ENVS = (
	"IPFS_DATASETS_PY_LLM_PROVIDER",
	"COMPLAINT_GENERATOR_LLM_PROVIDER",
	"LLM_ROUTER_PROVIDER",
	"COMPLAINT_LLM_PROVIDER",
	"COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER",
)
_CONSENT_STATUSES = {"implicit_local", "explicit_local", "explicit_grok"}


def complaint_data_class_inventory() -> Dict[str, Any]:
	"""Canonical inventory. Does not read session, evidence, export, or secret paths."""

	return {
		"contract": PRIVACY_POLICY_CONTRACT,
		"version": PRIVACY_POLICY_VERSION,
		"private_claim_fact_graph": [
			{"id": class_id, "description": description, "classification": "private"}
			for class_id, description in PRIVATE_DATA_CLASSES
		],
		"public_legal_source_graph": {
			"id": PUBLIC_LEGAL_SOURCE_CLASS[0],
			"description": PUBLIC_LEGAL_SOURCE_CLASS[1],
			"classification": "public",
			"distinct_from": "private_claim_fact_graph",
		},
		"at_rest_protection": PRIVACY_AT_REST_PROTECTION,
		"encryption_at_rest_blocks_remote_llm": False,
		"authenticates_tenant": False,
		"agent_context": {
			"fixtures_only": True,
			"excluded_path_classes": ["session", "evidence", "export", "secret"],
		},
	}


def _local_privacy_policy(user_id: str, case_id: str, *, consent_status: str = "implicit_local") -> Dict[str, Any]:
	return {
		"contract": PRIVACY_POLICY_CONTRACT,
		"version": PRIVACY_POLICY_VERSION,
		"user_id": str(user_id or ""),
		"case_id": str(case_id or ""),
		"processing_mode": PRIVACY_PROCESSING_LOCAL,
		"cloud_processing_enabled": False,
		"permitted_remote": None,
		"scope": PRIVACY_SCOPE_USER_CASE,
		"at_rest_protection": PRIVACY_AT_REST_PROTECTION,
		"encryption_at_rest_blocks_remote_llm": False,
		"authenticates_tenant": False,
		"consent": {"status": consent_status, "cloud_processing": False},
		"data_classes": {
			"private": [class_id for class_id, _description in PRIVATE_DATA_CLASSES],
			"public": [PUBLIC_LEGAL_SOURCE_CLASS[0]],
		},
		"agent_context": {
			"fixtures_only": True,
			"excluded_path_classes": ["session", "evidence", "export", "secret"],
		},
	}


def privacy_policy_for_mode(user_id: str, case_id: str, mode: str) -> Dict[str, Any]:
	normalized = str(mode or "").strip().lower()
	if normalized in {"local", "local_private"}:
		return _local_privacy_policy(user_id, case_id, consent_status="explicit_local")
	if normalized in {"grok", "grok_cloud"}:
		policy = _local_privacy_policy(user_id, case_id, consent_status="explicit_grok")
		policy["processing_mode"] = PRIVACY_PROCESSING_GROK
		policy["cloud_processing_enabled"] = True
		policy["consent"] = {"status": "explicit_grok", "cloud_processing": True}
		policy["permitted_remote"] = {
			"provider": PRIVACY_GROK_PROVIDER,
			"model": PRIVACY_GROK_MODEL,
		}
		return policy
	raise ValueError("privacy_denied:unknown_mode")


def _policy_rejection_reason(raw: Any, *, user_id: str, case_id: str) -> Optional[str]:
	if not isinstance(raw, Mapping):
		return "legacy_missing" if raw is None else PRIVACY_DENIAL_MALFORMED
	if str(raw.get("contract") or "") != PRIVACY_POLICY_CONTRACT:
		return PRIVACY_DENIAL_MALFORMED
	if str(raw.get("version") or "") != PRIVACY_POLICY_VERSION:
		return PRIVACY_DENIAL_VERSION
	if str(raw.get("scope") or "") != PRIVACY_SCOPE_USER_CASE:
		return PRIVACY_DENIAL_SCOPE_FIELD
	policy_user = str(raw.get("user_id") or "")
	policy_case = str(raw.get("case_id") or "")
	if not policy_user or not policy_case or policy_user != str(user_id or "") or policy_case != str(case_id or ""):
		return PRIVACY_DENIAL_CASE
	if raw.get("authenticates_tenant") is not False:
		return PRIVACY_DENIAL_MALFORMED
	if raw.get("encryption_at_rest_blocks_remote_llm") is not False:
		return PRIVACY_DENIAL_MALFORMED
	if str(raw.get("at_rest_protection") or "") != PRIVACY_AT_REST_PROTECTION:
		return PRIVACY_DENIAL_MALFORMED
	consent = raw.get("consent")
	if not isinstance(consent, Mapping) or str(consent.get("status") or "") not in _CONSENT_STATUSES:
		return PRIVACY_DENIAL_MALFORMED
	mode = str(raw.get("processing_mode") or "")
	cloud = raw.get("cloud_processing_enabled")
	permitted = raw.get("permitted_remote")
	consent_status = str(consent.get("status") or "")
	if mode == PRIVACY_PROCESSING_LOCAL:
		if cloud is not False or permitted is not None or consent.get("cloud_processing") is not False:
			return PRIVACY_DENIAL_MALFORMED
		if consent_status == "explicit_grok":
			return PRIVACY_DENIAL_MALFORMED
	elif mode == PRIVACY_PROCESSING_GROK:
		if cloud is not True or consent_status != "explicit_grok" or consent.get("cloud_processing") is not True:
			return PRIVACY_DENIAL_MALFORMED
		if not isinstance(permitted, Mapping):
			return PRIVACY_DENIAL_MALFORMED
		if set(permitted.keys()) != {"provider", "model"}:
			return PRIVACY_DENIAL_MALFORMED
		if str(permitted.get("provider") or "") != PRIVACY_GROK_PROVIDER:
			return PRIVACY_DENIAL_MALFORMED
		if str(permitted.get("model") or "") != PRIVACY_GROK_MODEL:
			return PRIVACY_DENIAL_MALFORMED
	else:
		return PRIVACY_DENIAL_MALFORMED
	data_classes = raw.get("data_classes")
	if not isinstance(data_classes, Mapping):
		return PRIVACY_DENIAL_MALFORMED
	if not isinstance(data_classes.get("private"), list) or data_classes["private"] != [class_id for class_id, _description in PRIVATE_DATA_CLASSES]:
		return PRIVACY_DENIAL_MALFORMED
	if not isinstance(data_classes.get("public"), list) or data_classes["public"] != [PUBLIC_LEGAL_SOURCE_CLASS[0]]:
		return PRIVACY_DENIAL_MALFORMED
	agent_context = raw.get("agent_context")
	if not isinstance(agent_context, Mapping) or agent_context.get("fixtures_only") is not True:
		return PRIVACY_DENIAL_MALFORMED
	if not isinstance(agent_context.get("excluded_path_classes"), list) or agent_context["excluded_path_classes"] != ["session", "evidence", "export", "secret"]:
		return PRIVACY_DENIAL_MALFORMED
	return None


def inspect_privacy_policy(raw: Any, *, user_id: str, case_id: str) -> Dict[str, Any]:
	"""Validate one serialized policy. Malformed input never enables cloud processing."""

	reason = _policy_rejection_reason(raw, user_id=user_id, case_id=case_id)
	if reason is None and isinstance(raw, Mapping):
		admitted = dict(raw)
		return {
			"admitted": True,
			"reason": "ok",
			"cloud_processing_enabled": bool(admitted.get("cloud_processing_enabled")),
			"policy": admitted,
		}
	load_reason = "legacy_missing" if reason == "legacy_missing" else str(reason or PRIVACY_DENIAL_MALFORMED)
	return {
		"admitted": False,
		"reason": load_reason,
		"cloud_processing_enabled": False,
		"policy": _local_privacy_policy(user_id, case_id),
	}


def coerce_effective_privacy_policy(raw: Any, *, user_id: str, case_id: str) -> Dict[str, Any]:
	inspection = inspect_privacy_policy(raw, user_id=user_id, case_id=case_id)
	return inspection["policy"]


def build_complaint_privacy_context(
	policy: Any,
	*,
	user_id: str,
	case_id: str,
	data_class: str,
) -> Dict[str, Any]:
	inspection = inspect_privacy_policy(policy, user_id=user_id, case_id=case_id)
	return {
		"contract": PRIVACY_CONTEXT_CONTRACT,
		"version": PRIVACY_POLICY_VERSION,
		"user_id": str(user_id or ""),
		"case_id": str(case_id or ""),
		"data_class": str(data_class or ""),
		"policy": inspection["policy"],
		"load": {
			"admitted": inspection["admitted"],
			"reason": inspection["reason"],
			"cloud_processing_enabled": inspection["cloud_processing_enabled"],
		},
	}


def _resolved_remote_target(provider: Optional[str], model_name: Optional[str]) -> tuple[str, str]:
	explicit_provider = str(provider or "").strip()
	explicit_model = str(model_name or "").strip()
	ambient: list[str] = []
	for name in _AMBIENT_PROVIDER_ENVS:
		value = os.getenv(name, "").strip()
		if value:
			ambient.append(value)
	unique = {item.lower() for item in ambient}
	if explicit_provider:
		resolved_provider = explicit_provider
	elif len(unique) == 1:
		resolved_provider = ambient[0]
	elif not unique:
		resolved_provider = ""
	else:
		resolved_provider = ""
	return resolved_provider, explicit_model


def _privacy_context_block_reason(
	context: Any,
	*,
	provider: Optional[str],
	model_name: Optional[str],
	options: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
	"""Return a stable denial code, or None when this call may reach preparation.

	A missing context keeps historical callers working. A present context is the
	first-party private boundary and is decided before provider preparation.
	"""

	if context is None:
		return None
	if not isinstance(context, Mapping):
		return PRIVACY_DENIAL_MALFORMED
	if str(context.get("contract") or "") != PRIVACY_CONTEXT_CONTRACT:
		return PRIVACY_DENIAL_MALFORMED
	if str(context.get("version") or "") != PRIVACY_POLICY_VERSION:
		return PRIVACY_DENIAL_VERSION
	data_class = str(context.get("data_class") or "")
	if data_class not in _KNOWN_DATA_CLASSES:
		return PRIVACY_DENIAL_MALFORMED
	user_id = str(context.get("user_id") or "")
	case_id = str(context.get("case_id") or "")
	inspection = inspect_privacy_policy(context.get("policy"), user_id=user_id, case_id=case_id)
	if not inspection["admitted"]:
		reason = str(inspection["reason"] or PRIVACY_DENIAL_MALFORMED)
		if reason == "legacy_missing":
			return PRIVACY_DENIAL_MALFORMED
		return reason
	resolved_provider, resolved_model = _resolved_remote_target(provider, model_name)
	exact_grok = (
		resolved_provider.strip().lower() == PRIVACY_GROK_PROVIDER
		and resolved_model == PRIVACY_GROK_MODEL
	)
	if not inspection["cloud_processing_enabled"]:
		return PRIVACY_DENIAL_CLOUD_DISABLED
	if not exact_grok:
		return PRIVACY_DENIAL_SCOPE
	if options and any(key not in _PRIVATE_GENERATION_OPTIONS and value is not None for key, value in options.items()):
		return PRIVACY_DENIAL_SCOPE
	return None


# Private calls are one pinned generation, not a configurable dispatch route.
# Opaque providers, allocation sessions, custom commands, routing URLs and
# trace destinations cannot inherit case consent.
_PRIVATE_GENERATION_OPTIONS = frozenset({
	"temperature", "max_tokens", "max_output_tokens", "timeout", "stop",
	"top_p", "top_k", "frequency_penalty", "presence_penalty", "seed",
	"response_format", "grok_max_turns",
	"allow_local_fallback", "allow_cross_provider_fallback",
})


def _private_generation_options(options: Mapping[str, Any]) -> Dict[str, Any]:
	return {
		**{key: value for key, value in options.items() if key in _PRIVATE_GENERATION_OPTIONS},
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
	}


__all__ = [
	"generate_text",
	"generate_text_via_router",
	"generate_text_with_metadata",
	"grok47_route_capability",
	"grok_cli_auth_present",
	"grok_cli_binary_present",
	"llm_router_status",
	"LLM_ROUTER_AVAILABLE",
	"LLM_ROUTER_ERROR",
	"HF_ROUTER_DEFAULT_BASE_URL",
	"PRIVACY_POLICY_CONTRACT",
	"PRIVACY_POLICY_VERSION",
	"PRIVACY_AT_REST_PROTECTION",
	"PRIVACY_GROK_PROVIDER",
	"PRIVACY_GROK_MODEL",
	"IntakeContractError",
	"INTAKE_REQUEST_OBJECT_SCHEMA",
	"INTAKE_REQUEST_SCHEMA_NAME",
	"INTAKE_REQUEST_SCHEMA_VERSION",
	"build_complaint_privacy_context",
	"classify_router_failure",
	"intake_request_response_format",
	"parse_intake_request",
	"coerce_effective_privacy_policy",
	"complaint_data_class_inventory",
	"inspect_privacy_policy",
	"privacy_policy_for_mode",
]
