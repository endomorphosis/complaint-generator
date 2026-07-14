"""Mike editor integration package.

Exposes the LLM router patch and editor adapter utilities so the complaint
workspace can programmatically reach the Mike frontend/backend layer and
enforce its router-ownership policy at every handoff boundary.
"""

from __future__ import annotations

from .llm_patch import apply_mike_llm_router_patch, MIKE_LLM_PATCH_VERSION

__all__ = [
    "apply_mike_llm_router_patch",
    "MIKE_LLM_PATCH_VERSION",
]
