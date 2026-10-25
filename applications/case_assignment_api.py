"""Invite and accept scoped lawyer assignments.

Owners choose a server-recorded lawyer and create a pending membership with an
explicit action scope. The recipient accepts that same scope or declines.
Pending, declined, expired, and removed states are visible to both parties.
Expiry is derived from the grant clock; it is not a status the client can set.

A lawyer role, a client-supplied role, or a guessed case identifier does not
open content. Ciphertext opens only after an accepted membership and a
recipient key grant, using operator-bound key sessions and artifacts. This
module does not send external messages and does not claim WebSocket or SSE.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from starlette.requests import Request

from applications.case_access import ASSIGNED_LAWYER_ACTIONS, CaseAccessError
from applications.case_directory import CaseDirectory, CaseDirectoryError
from applications.case_membership import CaseMembershipError, CaseMembershipStore
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_collaboration import (
    CaseResourceKeyGrantError,
    CaseResourceKeyGrantStore,
)
from integrations.private_storage import UserOwnedKeySession

TASK_ID = "CIMP-GUI-41"
ASSIGNMENT_LIMITATIONS = (
    "lawyer_role_alone_grants_nothing",
    "client_supplied_role_grants_nothing",
    "guessed_case_id_grants_nothing",
    "content_requires_accepted_membership_and_key_grant",
    "expiry_is_derived_not_client_status",
    "no_external_notification_delivery",
    "no_websocket_or_sse",
)
_REJECTED_BODY_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "is_member",
    "membership",
    "grant",
    "actions",
    "status",
    "accepted",
    "case_plaintext",
    "plaintext",
    "credentials",
    "credential",
    "narrative",
    "evidence",
    "browser_key",
    "data_key",
    "passphrase",
    "wrapped_ciphertext",
    "wrapped_nonce",
    "envelope",
    "key_material",
})
_VISIBLE = frozenset({"pending", "accepted", "declined", "expired", "removed"})


class CaseAssignmentError(Exception):
    """Fail-closed assignment error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseAssignmentError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseAssignmentError(code)
    return value


def _scope(value: Any) -> set[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise CaseAssignmentError("scope_required")
    if len(set(value)) != len(value):
        raise CaseAssignmentError("scope_required")
    granted = set(value)
    if not granted <= ASSIGNED_LAWYER_ACTIONS:
        raise CaseAssignmentError("action_not_permitted")
    return granted


class CaseAssignmentService:
    """HTTP-facing owner of membership invites and recipient key admission."""

    def __init__(
        self,
        *,
        principals: PrincipalStore,
        cases: CaseDirectory,
        memberships: CaseMembershipStore,
        key_grants: CaseResourceKeyGrantStore,
        sessions: Mapping[str, UserOwnedKeySession],
        clock: Callable[[], int],
    ) -> None:
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseAssignmentError("authority_owners")
        if not isinstance(memberships, CaseMembershipStore) or not isinstance(key_grants, CaseResourceKeyGrantStore):
            raise CaseAssignmentError("authority_owners")
        if not isinstance(sessions, Mapping) or not callable(clock):
            raise CaseAssignmentError("authority_owners")
        self._principals = principals
        self._cases = cases
        self._memberships = memberships
        self._key_grants = key_grants
        self._sessions = dict(sessions)
        self._clock = clock
        self._artifacts: dict[tuple[str, str, str], bytes] = {}
        self._admitted: dict[str, dict[str, str]] = {}

    def bind_artifact(self, *, case_id: str, artifact_kind: str, artifact_revision: str, envelope: bytes) -> None:
        """Operator binding. Request bodies cannot supply ciphertext."""

        if not isinstance(envelope, bytes) or not envelope:
            raise CaseAssignmentError("artifact_unavailable")
        key = (_label(case_id, "case_id"), _label(artifact_kind, "artifact_kind"), _label(artifact_revision, "artifact_revision"))
        self._artifacts[key] = envelope

    def list_lawyers(self, actor_principal_id: str) -> dict[str, Any]:
        self._active(actor_principal_id)
        lawyers = []
        for record in self._principals.recover():
            if record.status == "active" and "lawyer" in record.roles:
                lawyers.append({"principal_id": record.principal_id})
        return {
            "actor_principal_id": actor_principal_id,
            "lawyers": lawyers,
            "limitations": list(ASSIGNMENT_LIMITATIONS),
        }

    def invite(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        case_id = _label(payload.get("case_id"), "case_id")
        member_id = _label(payload.get("member_principal_id"), "member_principal_id")
        try:
            case = self._cases.select_case(actor_principal_id=actor, case_id=case_id)
        except CaseDirectoryError as exc:
            raise CaseAssignmentError("missing_case") from exc
        if case.owner_principal_id != actor:
            raise CaseAssignmentError("missing_case")
        supplied_tenant = payload.get("tenant_id", case.tenant_id)
        supplied_resource = payload.get("resource_id", case.resource_id)
        if supplied_tenant != case.tenant_id or supplied_resource != case.resource_id:
            raise CaseAssignmentError("missing_case")
        try:
            grant = self._memberships.invite(
                owner_principal_id=actor,
                member_principal_id=member_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                tenant_id=case.tenant_id,
                actions=_scope(payload.get("scope")),
                expires_at=payload.get("expires_at"),
                expected_case_revision=payload.get("expected_case_revision"),
                idempotency_key=_label(payload.get("idempotency_key"), "idempotency_key"),
            )
        except CaseMembershipError as exc:
            raise CaseAssignmentError(_invite_code(exc.code)) from exc
        return self._view(grant, actor)

    def list_assignments(self, actor_principal_id: str) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        rows = []
        for grant in self._memberships.recover():
            if actor not in {grant.owner_principal_id, grant.member_principal_id}:
                continue
            rows.append(self._view(grant, actor))
        rows.sort(key=lambda item: item["grant_id"])
        return {
            "actor_principal_id": actor,
            "assignments": rows,
            "states": sorted(_VISIBLE),
            "limitations": list(ASSIGNMENT_LIMITATIONS),
        }

    def accept(self, actor_principal_id: str, grant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._respond(actor_principal_id, grant_id, body, status="accepted")

    def decline(self, actor_principal_id: str, grant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._respond(actor_principal_id, grant_id, body, status="declined")

    def remove(self, actor_principal_id: str, grant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        grant = self._visible(actor, grant_id)
        if grant.owner_principal_id != actor:
            raise CaseAssignmentError("missing_grant")
        try:
            updated = self._memberships.remove(
                owner_principal_id=actor,
                grant_id=grant.grant_id,
                expected_version=payload.get("expected_version"),
            )
        except CaseMembershipError as exc:
            raise CaseAssignmentError(_decision_code(exc.code)) from exc
        return self._view(updated, actor)

    def issue_key_grant(self, actor_principal_id: str, grant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        grant = self._visible(actor, grant_id)
        if grant.owner_principal_id != actor or self._display(grant) != "accepted":
            raise CaseAssignmentError("membership_required")
        owner_session = self._sessions.get(actor)
        recipient_session = self._sessions.get(grant.member_principal_id)
        if not isinstance(owner_session, UserOwnedKeySession) or not isinstance(recipient_session, UserOwnedKeySession):
            raise CaseAssignmentError("key_owner_required")
        try:
            issued = self._key_grants.issue(
                actor_principal_id=actor,
                recipient_principal_id=grant.member_principal_id,
                membership_grant_id=grant.grant_id,
                membership_version=grant.version,
                case_id=grant.case_id,
                resource_id=grant.resource_id,
                tenant_id=grant.tenant_id,
                artifact_kind=_label(payload.get("artifact_kind"), "artifact_kind"),
                artifact_revision=_label(payload.get("artifact_revision"), "artifact_revision"),
                owner_session=owner_session,
                recipient_session=recipient_session,
                idempotency_key=_label(payload.get("idempotency_key"), "idempotency_key"),
            )
        except CaseResourceKeyGrantError as exc:
            raise CaseAssignmentError(_key_code(exc.code)) from exc
        self._admitted[grant.grant_id] = {
            "key_grant_id": issued.key_grant_id,
            "artifact_kind": issued.artifact_kind,
            "artifact_revision": issued.artifact_revision,
        }
        view = issued.public_view()
        view["limitations"] = list(ASSIGNMENT_LIMITATIONS)
        view["plaintext_available"] = False
        return view

    def open_content(self, actor_principal_id: str, grant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        grant = self._visible(actor, grant_id)
        if grant.member_principal_id != actor or self._display(grant) != "accepted":
            raise CaseAssignmentError("membership_required")
        if type(payload.get("expected_version")) is not int or payload.get("expected_version") != grant.version:
            raise CaseAssignmentError("revision_conflict")
        kind = _label(payload.get("artifact_kind"), "artifact_kind")
        revision = _label(payload.get("artifact_revision"), "artifact_revision")
        envelope = self._artifacts.get((grant.case_id, kind, revision))
        if envelope is None:
            raise CaseAssignmentError("artifact_unavailable")
        session = self._sessions.get(actor)
        if not isinstance(session, UserOwnedKeySession):
            raise CaseAssignmentError("key_owner_required")
        try:
            opened = self._key_grants.read_delegated(
                actor_principal_id=actor,
                membership_grant_id=grant.grant_id,
                membership_version=grant.version,
                key_grant_id=_label(payload.get("key_grant_id"), "key_grant_id"),
                case_id=grant.case_id,
                tenant_id=grant.tenant_id,
                resource_id=grant.resource_id,
                artifact_kind=kind,
                artifact_revision=revision,
                envelope=envelope,
                recipient_session=session,
            )
        except CaseResourceKeyGrantError as exc:
            raise CaseAssignmentError(_key_code(exc.code)) from exc
        plaintext = opened.get("data")
        if not isinstance(plaintext, bytes):
            raise CaseAssignmentError("content_unavailable")
        try:
            text = plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CaseAssignmentError("content_unavailable") from exc
        return {
            "actor_principal_id": actor,
            "grant_id": grant.grant_id,
            "key_grant_id": opened.get("key_grant_id"),
            "case_id": grant.case_id,
            "tenant_id": grant.tenant_id,
            "canonical_owner_principal_id": grant.tenant_id,
            "actor_is_encrypted_owner": False,
            "membership": "accepted",
            "key_grant": "admitted",
            "plaintext_available": True,
            "text": text,
            "limitations": list(ASSIGNMENT_LIMITATIONS),
        }

    def _respond(self, actor_principal_id: str, grant_id: str, body: Mapping[str, Any], *, status: str) -> dict[str, Any]:
        actor = self._active(actor_principal_id)
        payload = self._body(body)
        grant = self._visible(actor, grant_id)
        if grant.member_principal_id != actor:
            raise CaseAssignmentError("missing_grant")
        if self._display(grant) == "expired" and grant.status == "pending":
            raise CaseAssignmentError("grant_expired")
        if status == "accepted" and _scope(payload.get("scope")) != set(grant.actions):
            raise CaseAssignmentError("scope_mismatch")
        method = self._memberships.accept if status == "accepted" else self._memberships.decline
        try:
            updated = method(
                member_principal_id=actor,
                grant_id=grant.grant_id,
                expected_version=payload.get("expected_version"),
                idempotency_key=_label(payload.get("idempotency_key"), "idempotency_key"),
            )
        except CaseMembershipError as exc:
            raise CaseAssignmentError(_decision_code(exc.code)) from exc
        return self._view(updated, actor)

    def _visible(self, actor: str, grant_id: str):
        try:
            grant = self._memberships.load(_label(grant_id, "grant_id"))
        except CaseMembershipError as exc:
            raise CaseAssignmentError("missing_grant") from exc
        if actor not in {grant.owner_principal_id, grant.member_principal_id}:
            raise CaseAssignmentError("missing_grant")
        return grant

    def _view(self, grant, actor: str) -> dict[str, Any]:
        shown = self._display(grant)
        view = grant.public_view()
        view["state"] = shown
        view["scope"] = list(grant.actions)
        view["party"] = "owner" if actor == grant.owner_principal_id else "recipient"
        view["plaintext_available"] = False
        admitted = self._admitted.get(grant.grant_id)
        view["key_grant"] = "admitted" if admitted and shown == "accepted" else "required"
        if admitted and shown == "accepted":
            view["key_grant_id"] = admitted["key_grant_id"]
            view["artifact_kind"] = admitted["artifact_kind"]
            view["artifact_revision"] = admitted["artifact_revision"]
        view["actor_is_encrypted_owner"] = False
        view["canonical_owner_principal_id"] = grant.tenant_id
        view["limitations"] = list(ASSIGNMENT_LIMITATIONS)
        return view

    def _display(self, grant) -> str:
        if grant.status in {"declined", "removed"}:
            return grant.status
        if self._now() >= grant.expires_at:
            return "expired"
        if grant.status in {"pending", "accepted"}:
            return grant.status
        raise CaseAssignmentError("membership_required")

    def _body(self, body: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise CaseAssignmentError("request_body")
        if any(name in body for name in _REJECTED_BODY_FIELDS):
            raise CaseAssignmentError("request_cannot_mint_authority")
        if body.get("trusted_local") is True or body.get("trust") == "trusted_local":
            raise CaseAssignmentError("request_cannot_mint_authority")
        return body

    def _active(self, principal_id: str) -> str:
        identity = _label(principal_id, "unauthenticated")
        try:
            record = self._principals.load(identity)
        except PrincipalStoreError as exc:
            raise CaseAssignmentError("missing_principal") from exc
        if record.status != "active":
            raise CaseAssignmentError("inactive_principal")
        return record.principal_id

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise CaseAssignmentError("clock")
        return value


def _invite_code(code: str) -> str:
    if code in {"missing_case", "actor_not_owner", "tenant_mismatch", "resource_mismatch", "missing_principal"}:
        return "missing_case"
    return code


def _decision_code(code: str) -> str:
    if code in {"actor_not_member", "actor_not_owner", "missing_grant"}:
        return "missing_grant"
    return code


def _key_code(code: str) -> str:
    if code in {"membership_pending", "membership_required", "membership_declined", "membership_removed", "grant_expired"}:
        return code
    if code in {"actor_not_recipient", "missing_grant", "case_mismatch"}:
        return "missing_grant"
    return code


def assignment_http_status(code: str) -> int:
    if code in {"missing_case", "missing_grant", "missing_principal"}:
        return 404
    if code in {"revision_conflict", "replay_mismatch", "membership_replay"}:
        return 409
    if code in {"unauthenticated", "request_body"}:
        return 401
    if code == "assignment_unavailable":
        return 503
    return 403


def mount_case_assignments(app: Any) -> None:
    """Mount assignment routes. Catalog authentication runs before these handlers."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseAssignmentService:
        service = getattr(request.app.state, "case_assignments", None)
        if not isinstance(service, CaseAssignmentService):
            raise CaseAssignmentError("assignment_unavailable")

        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseAssignmentError("unauthenticated")
        return actor

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: CaseAssignmentError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=assignment_http_status(exc.code))

    @app.get("/api/cases/lawyers")
    async def assignment_lawyers(request: Request):
        try:
            return JSONResponse(_service(request).list_lawyers(_actor(request)))
        except CaseAssignmentError as exc:
            return _fail(exc)

    @app.get("/api/cases/assignments")
    async def assignment_list(request: Request):
        try:
            return JSONResponse(_service(request).list_assignments(_actor(request)))
        except CaseAssignmentError as exc:
            return _fail(exc)

    @app.post("/api/cases/assignments")
    async def assignment_invite(request: Request):
        try:
            created = _service(request).invite(_actor(request), _material(request))
        except CaseAssignmentError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.post("/api/cases/assignments/{grant_id}/accept")
    async def assignment_accept(grant_id: str, request: Request):
        try:
            return JSONResponse(_service(request).accept(_actor(request), grant_id, _material(request)))
        except CaseAssignmentError as exc:
            return _fail(exc)

    @app.post("/api/cases/assignments/{grant_id}/decline")
    async def assignment_decline(grant_id: str, request: Request):
        try:
            return JSONResponse(_service(request).decline(_actor(request), grant_id, _material(request)))
        except CaseAssignmentError as exc:
            return _fail(exc)

    @app.post("/api/cases/assignments/{grant_id}/remove")
    async def assignment_remove(grant_id: str, request: Request):
        try:
            return JSONResponse(_service(request).remove(_actor(request), grant_id, _material(request)))
        except CaseAssignmentError as exc:
            return _fail(exc)

    @app.post("/api/cases/assignments/{grant_id}/key-grant")
    async def assignment_key_grant(grant_id: str, request: Request):
        try:
            created = _service(request).issue_key_grant(_actor(request), grant_id, _material(request))
        except CaseAssignmentError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.post("/api/cases/assignments/{grant_id}/content")
    async def assignment_content(grant_id: str, request: Request):
        try:
            return JSONResponse(_service(request).open_content(_actor(request), grant_id, _material(request)))
        except CaseAssignmentError as exc:
            return _fail(exc)
        except CaseAccessError as exc:
            return JSONResponse({"error": exc.code}, status_code=403)
