"""Synthetic capture recipes for the complaint UX screenshot matrix.

Screenshots are produced through the public ASGI app and the pinned
Chromium/Node harness. This module does not read operator profiles, invent
evidence bytes, or leave a browser running.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from applications.admin_api import OperationalAdminService
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "capture_contract.json"
BASELINE_DIR = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "baseline"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ADMIN_CREDENTIAL = "synthetic-admin-credential"
CHAT_FACT = "Synthetic chat fact about a fictional employer and no real person."
DRAFT_NOTE = "Synthetic correspondence that stays in the composer until a real send."
OWNER_CREDENTIAL = "synthetic-owner-credential"
LAWYER_CREDENTIAL = "synthetic-lawyer-credential"
STRANGER_CREDENTIAL = "synthetic-stranger-credential"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix_cells(contract: dict | None = None) -> list[dict]:
    """One cell per surface, phase, and declared viewport."""

    contract = load_contract() if contract is None else contract
    cells = []
    for surface in contract["surfaces"]:
        for phase in contract["phases"]:
            for name, size in contract["viewports"].items():
                cells.append({
                    "surface": surface["id"],
                    "role": surface["role"],
                    "route": surface["route"],
                    "phase": phase,
                    "viewport": name,
                    "width": size["width"],
                    "height": size["height"],
                    "dom": surface["before_dom"] if phase == "before" else surface["after_dom"],
                    "baseline_ids": list(surface["baseline_ids"]),
                })
    return cells


def synthetic_capture_world(tmp_path: Path):
    """Journey owners plus a separate operational-admin principal.

    The admin credential is an operator fixture secret. It is not read from a
    request body and it does not grant case content.
    """

    world = owner_lawyer_journey_world(tmp_path)
    admin = world.principals.install_server_role(role="operational_admin")
    world.sessions._adapter._credentials[ADMIN_CREDENTIAL] = admin.principal_id
    world.app.state.operational_admin = OperationalAdminService(
        principals=world.principals,
        sessions=world.sessions,
        clock=lambda: int(world.now["t"]),
        audit_principal_ids=(admin.principal_id,),
        memberships=world.memberships,
        cases=world.cases,
        assignments=world.assignments,
    )
    world.admin = admin
    world.admin_credential = ADMIN_CREDENTIAL
    return world


def refuse_invented_evidence(record: dict) -> None:
    """A capture may describe a surface. It may not supply evidence bytes."""

    if not isinstance(record, dict):
        raise ValueError("capture_record_required")
    if record.get("invented_evidence") or record.get("evidence_bytes") or record.get("real_user_data"):
        raise ValueError("invented_or_real_evidence_refused")
    source = record.get("source")
    if source not in {"public_asgi_handler", "pinned_chromium_pipe"}:
        raise ValueError("capture_source_refused")
    if record.get("mock_api_used") or record.get("diagnostic_test_panels_mounted"):
        raise ValueError("diagnostic_capture_refused")
    route = record.get("route")
    if not isinstance(route, str) or not route.startswith("/"):
        raise ValueError("capture_route_refused")


def assert_png(payload: bytes, *, minimum: int = 800) -> str:
    if not isinstance(payload, (bytes, bytearray)) or not bytes(payload).startswith(PNG_MAGIC):
        raise ValueError("screenshot_not_png")
    if len(payload) < minimum:
        raise ValueError("screenshot_blank_or_truncated")
    return hashlib.sha256(payload).hexdigest()


# Experience contract reflow width. The capture matrix records 1440, 768, and 390.
EXPERIENCE_REFLOW_WIDTH = 320
VISUAL_STATE_VARIANTS = ("loading", "empty", "error", "locked", "stale", "revoked")


def declared_visual_widths(contract: dict | None = None) -> list[dict]:
    """Capture-contract viewports plus the experience-contract 320px reflow."""

    contract = load_contract() if contract is None else contract
    widths = []
    for name, size in contract["viewports"].items():
        widths.append({"name": name, "width": int(size["width"]), "height": int(size["height"]), "source": "capture_contract"})
    widths.append({
        "name": "reflow-320",
        "width": EXPERIENCE_REFLOW_WIDTH,
        "height": 800,
        "source": "experience_contract",
    })
    return widths


def baseline_manifest() -> dict:
    return json.loads((BASELINE_DIR / "screenshot_manifest.json").read_text(encoding="utf-8"))


# Public complaint journey. A completed screen is not legal sufficiency or a filing.
JOURNEY_STAGES = (
    "original_complaint",
    "adaptive_question",
    "corrected_factual_graph",
    "private_annotated_evidence",
    "source_bound_legal_requirement",
    "cited_draft",
    "lawyer_message",
    "lawyer_review",
    "owner_acceptance",
    "cold_resume",
)
JOURNEY_FAILURES = (
    "unresolved",
    "unknown",
    "cancelled",
    "provider",
    "source",
    "proof",
    "storage",
    "unauthorized",
)


def complete_journey_world(tmp_path: Path):
    """Journey owners with the private evidence workbench mounted.

    Document routes stay the production draft owner. They are attached here
    because the shared journey app leaves them off; this does not invent a
    second interview or case database.
    """

    from applications.document_api import attach_document_routes
    from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend

    world = synthetic_capture_world(tmp_path)
    backend = MemoryByteBackend()
    world.app.state.evidence_workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        tmp_path / "evidence-root",
    )
    world.evidence_backend = backend
    attach_document_routes(world.app, world.service)
    return world


def assert_success_is_not_filing(payload: dict) -> None:
    """A successful journey payload must not claim sufficiency or a court filing."""

    if not isinstance(payload, dict):
        raise ValueError("journey_payload_required")
    if payload.get("legal_sufficiency") is True or payload.get("court_filed") is True:
        raise ValueError("success_claimed_legal_sufficiency")
    if payload.get("automatic_court_filing") is True or payload.get("governing_legal_authority") is True:
        raise ValueError("success_claimed_filing_or_governing_law")
    nested = payload.get("readiness")
    if isinstance(nested, dict) and (nested.get("legal_sufficiency") is True or nested.get("court_filed") is True):
        raise ValueError("success_claimed_legal_sufficiency")
