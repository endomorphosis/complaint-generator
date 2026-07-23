"""Mike LLM router monkey-patch.

The Mike editor is a TypeScript application whose backend (``backend/src/lib/llm/``)
routes generation through whichever LLM provider it resolves at request time.
The workspace **owns** the router policy; Mike is an editing surface only.

This module provides:

1. ``apply_mike_llm_router_patch(handoff_payload)`` — mutates a handoff payload
   dict in-place so that every field that governs Mike's generation strategy
   points back to the workspace ``llm_router``.  The patch is entirely additive:
   it does not remove existing keys.

2. A JSON descriptor (``MIKE_LLM_PATCH_DESCRIPTOR``) that can be embedded in
   the handoff payload to give the Mike frontend a machine-readable record of
   which patch was applied and when.

The actual enforcement on the TypeScript side is done via the MCP client
boundary (``backend/src/lib/mcp/client.ts``):  Mike calls the workspace MCP
server for generation tasks, and the workspace MCP server always routes through
``generate_text_with_metadata``.  This Python-side patch strengthens the same
invariant by:

* Marking every ``narrow_adapter_boundary`` flag as True.
* Recording ``patched_by`` / ``patched_at`` metadata.
* Setting ``must_route_generation_through_workspace_llm_router`` in the
  ``non_negotiable_constraints`` block.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from integrations.ipfs_datasets.llm import (
    LLM_ROUTER_AVAILABLE,
    LLM_ROUTER_ERROR,
    generate_text_with_metadata,
)

MIKE_LLM_PATCH_VERSION = "mike-llm-router-patch-v1"

MIKE_LLM_PATCH_DESCRIPTOR: Dict[str, Any] = {
    "patch_version": MIKE_LLM_PATCH_VERSION,
    "patch_module": "integrations.mike.llm_patch",
    "enforcement_boundary": "workspace_mcp_server",
    "generation_adapter": "integrations.ipfs_datasets.llm.generate_text_with_metadata",
    "router_owned_by": "complaint_generator",
    "mike_role": "editing_surface_only",
    "policy_fields_enforced": [
        "router_policy.centralized_policy.*",
        "router_policy.narrow_adapter_boundary.*",
        "non_negotiable_constraints.must_route_generation_through_workspace_llm_router",
    ],
}


def apply_mike_llm_router_patch(handoff_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Inject workspace llm_router ownership into *handoff_payload* in-place.

    The function:

    * Ensures every ``centralized_policy`` flag inside ``router_policy`` is True.
    * Ensures every ``narrow_adapter_boundary`` flag is True.
    * Records patch metadata (version, timestamp, router availability).
    * Sets ``must_route_generation_through_workspace_llm_router`` in
      ``non_negotiable_constraints``.

    Returns the same dict (mutated) for fluent chaining.
    """
    patched_at = datetime.now(tz=timezone.utc).isoformat()

    router_policy = handoff_payload.setdefault("router_policy", {})
    centralized_policy = router_policy.setdefault("centralized_policy", {})
    centralized_policy["router_selection_in_workspace"] = True
    centralized_policy["model_selection_in_workspace"] = True
    centralized_policy["safety_policy_in_workspace"] = True
    centralized_policy["grounding_policy_in_workspace"] = True

    narrow = router_policy.setdefault("narrow_adapter_boundary", {})
    narrow["mike_requests_generation_via_workspace"] = True
    narrow["mike_does_not_choose_provider"] = True
    narrow["mike_does_not_choose_model"] = True

    router_policy["patched_by"] = MIKE_LLM_PATCH_VERSION
    router_policy["patched_at"] = patched_at
    router_policy["llm_router_available"] = LLM_ROUTER_AVAILABLE
    router_policy["llm_router_error"] = str(LLM_ROUTER_ERROR or "") or None

    constraints = handoff_payload.setdefault("non_negotiable_constraints", {})
    constraints["must_route_generation_through_workspace_llm_router"] = True

    handoff_payload.setdefault("mike_llm_patch", {}).update(
        {
            **MIKE_LLM_PATCH_DESCRIPTOR,
            "patched_at": patched_at,
            "llm_router_available": LLM_ROUTER_AVAILABLE,
        }
    )

    return handoff_payload


def get_router_generate_fn():
    """Return the workspace generation function for callers that want a handle."""
    return generate_text_with_metadata


__all__ = [
    "MIKE_LLM_PATCH_VERSION",
    "MIKE_LLM_PATCH_DESCRIPTOR",
    "apply_mike_llm_router_patch",
    "get_router_generate_fn",
]
