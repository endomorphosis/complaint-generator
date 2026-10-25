"""Authorized case creation, listing, reading, and selection.

The authenticated browser principal is the only actor. A request ``user_id``
is never a directory selector and never widens the result. Newly created cases
stay owner-only: this surface does not invite collaborators or mint key grants.
Explicit membership that already exists on ``CaseActionAuthorizer`` may name a
case, but missing key grants stay closed and ciphertext is not opened.

Each case keeps its own sealed revision and unresolved gaps. Selecting another
case clears that actor's transient UI draft and does not rewrite the other
case's envelope.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from starlette.requests import Request

from applications.case_access import CaseAccessError, CaseActionAuthorizer
from applications.case_directory import (
    MEMBERSHIP_OWNER_ONLY,
    CaseDirectory,
    CaseDirectoryError,
    CaseNamespace,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateStorageError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-08"
CATALOG_LIMITATIONS = (
    "newly_created_cases_are_owner_only",
    "key_grants_are_not_issued_here",
    "explicit_membership_without_a_key_grant_does_not_open_ciphertext",
    "unknown_identifiers_do_not_enumerate_other_users",
)
COLLABORATION_FIELDS = frozenset({
    "collaborators",
    "members",
    "memberships",
    "grants",
    "grant",
    "invite",
    "invitees",
    "share_with",
    "lawyer_principal_id",
    "assigned_lawyer",
})
ARTIFACT_KIND = "case-ui-revision"
_MAX_GAPS = 32
_MAX_GAP_LENGTH = 200
_MAX_DRAFT = 4000


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass
class _TransientUI:
    selected_case_id: str | None = None
    draft: str = ""


@dataclass
class _SealedRevision:
    content_revision: int
    envelope: bytes
    gaps: tuple[str, ...]
    label: str


class CaseCatalog:
    """Owner-scoped catalog over ``CaseDirectory`` plus per-case sealed UI state."""

    def __init__(self, cases: CaseDirectory, authorizer: CaseActionAuthorizer, *, key: bytes, key_id: str) -> None:
        if not isinstance(cases, CaseDirectory) or not isinstance(authorizer, CaseActionAuthorizer):
            raise CaseAccessError("authority_owners")
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseAccessError("key_material")
        if not isinstance(key_id, str) or key_id.strip() == "" or key_id != key_id.strip():
            raise CaseAccessError("key_id")
        self._cases = cases
        self._authorizer = authorizer
        self._key = bytes(key)
        self._key_id = key_id
        self._sealed: dict[tuple[str, str, str], _SealedRevision] = {}
        self._ui: dict[str, _TransientUI] = {}

    def create(self, actor_principal_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = self._body(body)
        if any(name in payload for name in COLLABORATION_FIELDS):
            raise CaseAccessError("collaboration_not_available")
        actor = self._actor(actor_principal_id)
        supplied = payload.get("user_id")
        if supplied is not None and supplied != actor:
            raise CaseAccessError("user_id_not_a_selector")
        label = payload.get("label", "")
        if not isinstance(label, str) or len(label) > _MAX_GAP_LENGTH:
            raise CaseAccessError("label")
        try:
            record = self._cases.create_case(
                actor_principal_id=actor,
                supplied_user_id=actor if isinstance(supplied, str) else None,
            )
        except CaseDirectoryError as exc:
            raise CaseAccessError(exc.code) from exc
        if record.membership != MEMBERSHIP_OWNER_ONLY or record.owner_principal_id != actor:
            raise CaseAccessError("owner_only")
        self._write_sealed(record, content_revision=1, gaps=(), label=label)
        decision = self._authorize_owned(actor, record, action="case.read")
        return self._owner_view(decision, record, switched=False)

    def list_cases(self, actor_principal_id: str) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        try:
            records = self._cases.list_cases(actor_principal_id=actor)
        except CaseDirectoryError as exc:
            raise CaseAccessError(exc.code) from exc
        cases = []
        for record in records:
            if record.owner_principal_id != actor or record.membership != MEMBERSHIP_OWNER_ONLY:
                continue
            decision = self._authorize_owned(actor, record, action="case.read")
            cases.append(self._owner_view(decision, record, switched=False))
        return {
            "actor_principal_id": actor,
            "cases": cases,
            "membership": MEMBERSHIP_OWNER_ONLY,
            "limitations": list(CATALOG_LIMITATIONS),
        }

    def read(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._open(actor_principal_id, case_id, body, action="case.read", switching=False)

    def select(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._open(actor_principal_id, case_id, body, action="case.select", switching=True)

    def set_transient(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        draft = payload.get("draft", "")
        if not isinstance(draft, str) or len(draft) > _MAX_DRAFT:
            raise CaseAccessError("transient_draft")
        ui = self._ui.setdefault(actor, _TransientUI())
        if ui.selected_case_id != case_id:
            raise CaseAccessError("case_not_selected")
        # Confirm the selected id is still this actor's case before keeping text.
        self.read(actor, case_id, {})
        ui.draft = draft
        return {"actor_principal_id": actor, "selected_case_id": case_id, "transient": {"draft": draft}}

    def set_gaps(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        record = self._owned(actor, case_id)
        if record is None:
            raise CaseAccessError("missing_case")
        decision = self._authorize_owned(actor, record, action="case.update")
        if decision.membership != "owner":
            raise CaseAccessError("key_grant_required")
        expected = payload.get("expected_content_revision")
        if type(expected) is not int:
            raise CaseAccessError("encrypted_revision_conflict")
        gaps = self._gaps(payload.get("unresolved_gaps"))
        sealed = self._sealed.get(self._key_for(record))
        if sealed is None or sealed.content_revision != expected:
            raise CaseAccessError("encrypted_revision_conflict")
        self._write_sealed(record, content_revision=sealed.content_revision + 1, gaps=gaps, label=sealed.label)
        return self._owner_view(decision, record, switched=False)

    def session(self, actor_principal_id: str) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        ui = self._ui.get(actor) or _TransientUI()
        listed = self.list_cases(actor)
        return {
            "actor_principal_id": actor,
            "selected_case_id": ui.selected_case_id,
            "transient": {"draft": ui.draft},
            "cases": listed["cases"],
            "membership": MEMBERSHIP_OWNER_ONLY,
            "limitations": list(CATALOG_LIMITATIONS),
        }

    def sealed_envelope(self, actor_principal_id: str, case_id: str) -> bytes:
        """Return the actor's own sealed revision bytes. Foreign ids raise ``missing_case``."""

        actor = self._actor(actor_principal_id)
        record = self._owned(actor, case_id)
        if record is None:
            raise CaseAccessError("missing_case")
        self._authorize_owned(actor, record, action="case.read")
        sealed = self._sealed.get(self._key_for(record))
        if sealed is None:
            raise CaseAccessError("missing_case")
        return sealed.envelope

    def _open(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any] | None, *, action: str, switching: bool) -> dict[str, Any]:
        actor = self._actor(actor_principal_id)
        payload = self._body(body)
        if any(name in payload for name in COLLABORATION_FIELDS):
            raise CaseAccessError("collaboration_not_available")
        if payload.get("user_id") not in {None, actor}:
            raise CaseAccessError("user_id_not_a_selector")
        record = self._owned(actor, case_id)
        if record is not None:
            used = "case.select" if switching else action
            decision = self._authorize_owned(actor, record, action=used, body=payload)
            view = self._owner_view(decision, record, switched=False)
            if switching:
                view.update(self._switch(actor, record.case_id))
            return view
        decision = self._authorize_explicit(actor, case_id, payload, action="case.read" if switching else action)
        if decision.membership == "owner":
            raise CaseAccessError("missing_case")
        # Policy membership is not a key grant. Do not open or copy ciphertext.
        if switching:
            switched = self._switch(actor, decision.case_id)
        else:
            switched = {"transient_cleared": False, "transient": {"draft": (self._ui.get(actor) or _TransientUI()).draft}}
        return {
            "actor_principal_id": actor,
            "tenant_id": decision.tenant_id,
            "case_id": decision.case_id,
            "resource_id": decision.resource_id,
            "directory_revision": decision.revision,
            "membership": decision.membership,
            "actor_is_encrypted_owner": decision.actor_is_encrypted_owner,
            "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            "plaintext_available": False,
            "key_grant": "required",
            "limitations": list(CATALOG_LIMITATIONS),
            **switched,
        }

    def _switch(self, actor: str, case_id: str) -> dict[str, Any]:
        ui = self._ui.setdefault(actor, _TransientUI())
        switched = ui.selected_case_id != case_id
        if switched:
            ui.draft = ""
        ui.selected_case_id = case_id
        return {"transient_cleared": switched, "selected_case_id": case_id, "transient": {"draft": ui.draft}}

    def _authorize_owned(self, actor: str, record: CaseNamespace, *, action: str, body: Mapping[str, Any] | None = None) -> Any:
        payload = body or {}
        tenant_id = payload.get("tenant_id", record.tenant_id)
        resource_id = payload.get("resource_id", record.resource_id)
        revision = payload.get("expected_revision", record.revision)
        if not isinstance(tenant_id, str) or not isinstance(resource_id, str) or type(revision) is not int:
            raise CaseAccessError("revision_conflict")
        return self._authorizer.authorize(
            boundary="http",
            actor_principal_id=actor,
            tenant_id=tenant_id,
            case_id=record.case_id,
            resource_id=resource_id,
            action=action,
            expected_revision=revision,
            trust="authenticated",
        )

    def _authorize_explicit(self, actor: str, case_id: str, payload: Mapping[str, Any], *, action: str) -> Any:
        tenant_id = payload.get("tenant_id")
        resource_id = payload.get("resource_id")
        revision = payload.get("expected_revision")
        membership_revision = payload.get("expected_membership_revision")
        if not isinstance(tenant_id, str) or tenant_id == "" or not isinstance(resource_id, str) or resource_id == "":
            raise CaseAccessError("missing_case")
        if type(revision) is not int:
            raise CaseAccessError("missing_case")
        if membership_revision is not None and type(membership_revision) is not int:
            raise CaseAccessError("missing_case")
        try:
            return self._authorizer.authorize(
                boundary="http",
                actor_principal_id=actor,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_revision=revision,
                expected_membership_revision=membership_revision if type(membership_revision) is int else None,
                trust="authenticated",
            )
        except CaseAccessError as exc:
            if exc.code in {"tenant_mismatch", "resource_mismatch", "revision_conflict", "membership_required", "action_not_permitted"}:
                raise CaseAccessError("missing_case") from exc
            raise

    def _owned(self, actor: str, case_id: str) -> CaseNamespace | None:
        try:
            return self._cases.select_case(actor_principal_id=actor, case_id=case_id)
        except CaseDirectoryError as exc:
            if exc.code == "missing_case":
                return None
            raise CaseAccessError(exc.code) from exc

    def _owner_view(self, decision: Any, record: CaseNamespace, *, switched: bool) -> dict[str, Any]:
        sealed = self._sealed[self._key_for(record)]
        opened = self._open_sealed(record, sealed)
        return {
            "actor_principal_id": decision.actor_principal_id,
            "tenant_id": record.tenant_id,
            "case_id": record.case_id,
            "resource_id": record.resource_id,
            "directory_revision": record.revision,
            "encrypted_content_revision": opened["content_revision"],
            "envelope_sha256": hashlib.sha256(sealed.envelope).hexdigest(),
            "unresolved_gaps": list(opened["unresolved_gaps"]),
            "label": opened["label"],
            "membership": MEMBERSHIP_OWNER_ONLY,
            "actor_is_encrypted_owner": decision.actor_is_encrypted_owner,
            "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            "plaintext_available": True,
            "key_grant": "owner",
            "transient_cleared": switched,
            "limitations": list(CATALOG_LIMITATIONS),
        }

    def _write_sealed(self, record: CaseNamespace, *, content_revision: int, gaps: tuple[str, ...], label: str) -> None:
        document = {
            "content_revision": content_revision,
            "unresolved_gaps": list(gaps),
            "label": label,
            "membership": MEMBERSHIP_OWNER_ONLY,
        }
        binding = self._binding(record, content_revision)
        access = _CanonicalAccess("authenticated", record.tenant_id, record.case_id)
        assert_access_matches_binding(access, binding)
        envelope = seal_private_artifact(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            binding=binding,
            key=self._key,
            key_id=self._key_id,
        )
        self._sealed[self._key_for(record)] = _SealedRevision(content_revision, envelope, gaps, label)

    def _open_sealed(self, record: CaseNamespace, sealed: _SealedRevision) -> dict[str, Any]:
        binding = self._binding(record, sealed.content_revision)
        access = _CanonicalAccess("authenticated", record.tenant_id, record.case_id)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(sealed.envelope, binding=binding, key=self._key, expected_key_id=self._key_id)
            document = json.loads(plaintext.decode("utf-8"))
        except (PrivateArtifactIntegrityError, PrivateStorageError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CaseAccessError("missing_key") from exc
        if not isinstance(document, dict) or document.get("content_revision") != sealed.content_revision:
            raise CaseAccessError("encrypted_revision_conflict")
        return document

    def _binding(self, record: CaseNamespace, content_revision: int) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=record.tenant_id,
            case_id=record.case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(content_revision),
            principal_id=record.tenant_id,
        )

    def _key_for(self, record: CaseNamespace) -> tuple[str, str, str]:
        return (record.tenant_id, record.case_id, record.resource_id)

    def _actor(self, actor_principal_id: str) -> str:
        if not isinstance(actor_principal_id, str) or actor_principal_id.strip() == "":
            raise CaseAccessError("unauthenticated")
        return actor_principal_id

    def _body(self, body: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if body is None:
            return {}
        if not isinstance(body, Mapping):
            raise CaseAccessError("request_body")
        return body

    def _gaps(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or len(value) > _MAX_GAPS:
            raise CaseAccessError("unresolved_gaps")
        gaps = []
        for item in value:
            if not isinstance(item, str) or item.strip() == "" or item != item.strip() or len(item) > _MAX_GAP_LENGTH:
                raise CaseAccessError("unresolved_gaps")
            gaps.append(item)
        return tuple(gaps)


def cases_template_text() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "templates" / "cases.html").read_text(encoding="utf-8")


def mount_case_catalog(app: Any) -> None:
    """Mount catalog routes. The middleware authenticates before these run."""

    from fastapi.responses import HTMLResponse, JSONResponse

    def _fail(exc: CaseAccessError) -> JSONResponse:
        status = {
            "missing_case": 404,
            "encrypted_revision_conflict": 409,
            "revision_conflict": 409,
            "case_catalog_unavailable": 503,
            "unauthenticated": 401,
            "authorizer_required": 401,
        }.get(exc.code, 403)
        return JSONResponse({"error": exc.code}, status_code=status)

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseAccessError("unauthenticated")
        return actor

    def _catalog(request: Any) -> CaseCatalog:
        catalog = getattr(request.app.state, "case_catalog", None)
        if not isinstance(catalog, CaseCatalog):
            raise CaseAccessError("case_catalog_unavailable")
        return catalog

    def _material(request: Any) -> dict[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        if isinstance(material, dict):
            return material
        return {}

    @app.get("/cases")
    async def cases_page():
        return HTMLResponse(cases_template_text())

    @app.get("/api/cases/session")
    async def case_session(request: Request):
        try:
            return JSONResponse(_catalog(request).session(_actor(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.get("/api/cases")
    async def case_list(request: Request):
        try:
            return JSONResponse(_catalog(request).list_cases(_actor(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases")
    async def case_create(request: Request):
        try:
            created = _catalog(request).create(_actor(request), _material(request))
        except CaseAccessError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.get("/api/cases/{case_id}")
    async def case_read(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).read(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/select")
    async def case_select(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).select(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/transient")
    async def case_transient(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).set_transient(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/gaps")
    async def case_gaps(case_id: str, request: Request):
        try:
            return JSONResponse(_catalog(request).set_gaps(_actor(request), case_id, _material(request)))
        except CaseAccessError as exc:
            return _fail(exc)
