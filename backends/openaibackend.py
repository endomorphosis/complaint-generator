"""Deprecated alias for `backends.openai`.

This module name is preserved because older code imports
`backends.openaibackend.OpenAIBackend`.
"""

from __future__ import annotations

import warnings

from .openai import OpenAIBackend


warnings.warn(
	"`backends.openaibackend` is deprecated; import `backends.openai` or, preferably, use `backends.LLMRouterBackend`.",
	DeprecationWarning,
	stacklevel=2,
)
