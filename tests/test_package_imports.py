"""Package import smoke tests for runtime ownership metadata."""

from lib.runtime_ownership import (
    RUNTIME_ENTRYPOINT_GROUPS,
    VALID_RUNTIME_ROLES,
    entrypoint_groups_by_role,
    module_ownership_summary,
)


def test_runtime_entrypoint_groups_cover_required_roles() -> None:
    assert set(RUNTIME_ENTRYPOINT_GROUPS) == set(VALID_RUNTIME_ROLES)
    assert set(entrypoint_groups_by_role()) == {"cli", "web", "mediator", "workflow"}
    for role in VALID_RUNTIME_ROLES:
        assert RUNTIME_ENTRYPOINT_GROUPS[role], f"missing runtime entrypoints for role {role}"


def test_largest_runtime_modules_have_ownership_records() -> None:
    modules = {row["module_path"]: row for row in module_ownership_summary()}

    for module_path in (
        "applications.complaint_workspace",
        "scripts.synthesize_hacc_complaint",
        "mediator.mediator",
        "complaint_phases.denoiser",
    ):
        record = modules[module_path]
        assert record["owner"]
        assert record["primary_responsibility"]
        assert record["entrypoints"], f"missing entrypoints for {module_path}"

