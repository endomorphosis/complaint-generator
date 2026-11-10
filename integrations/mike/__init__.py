"""Mike editor integration package.

Exposes the LLM router patch, editor adapter utilities, and skill asset loader
so the complaint workspace can programmatically reach the Mike frontend/backend
layer and enforce its router-ownership policy at every handoff boundary.
"""

import importlib

__all__ = [
    "apply_mike_llm_router_patch",
    "MIKE_LLM_PATCH_VERSION",
    "load_skill",
    "list_skill_ids",
    "SKILLS_DIR",
]

_EXPORTS = {
    "apply_mike_llm_router_patch": "llm_patch",
    "MIKE_LLM_PATCH_VERSION": "llm_patch",
    "load_skill": "skills",
    "list_skill_ids": "skills",
    "SKILLS_DIR": "skills",
}


def __getattr__(name: str):
    owner = _EXPORTS.get(name)
    if owner is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module("." + owner, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
