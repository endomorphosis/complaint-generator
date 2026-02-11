"""Deprecated legacy OpenAI backend.

This repository is transitioning to the router-first architecture.

Prefer:
  - `backends.llm_router_backend.LLMRouterBackend`
  - or calling `ipfs_datasets_py.llm_router.generate_text` directly.

This module remains importable for backward compatibility, but it routes
through `LLMRouterBackend` and emits a DeprecationWarning.
"""

from __future__ import annotations

import warnings
from typing import Any, Mapping

from .llm_router_backend import LLMRouterBackend


warnings.warn(
	"`backends.openai.OpenAIBackend` is deprecated in complaint-generator; "
	"use `backends.LLMRouterBackend` (ipfs_datasets_py.llm_router) instead.",
	DeprecationWarning,
	stacklevel=2,
)


class OpenAIBackend(LLMRouterBackend):
	"""Compatibility wrapper that routes OpenAI-style configs via llm_router."""

	def __init__(
		self,
		id: str,
		api_key: str | None = None,
		engine: str | None = None,
		**config: Any,
	):
		# `api_key` is intentionally ignored; llm_router providers read secrets from env.
		if api_key:
			warnings.warn(
				"`api_key` passed to OpenAIBackend is ignored; set OPENAI_API_KEY in the environment instead.",
				DeprecationWarning,
				stacklevel=2,
			)

		model = config.pop("model", None) or engine
		super().__init__(id=id, provider=config.pop("provider", "openai"), model=model, **config)

	def __call__(self, text: str | Mapping[str, Any]):
		# Accept a few legacy shapes (string prompt is the canonical path).
		if isinstance(text, dict):
			text = str(text.get("prompt") or text.get("inputs") or "")
		return super().__call__(str(text))
