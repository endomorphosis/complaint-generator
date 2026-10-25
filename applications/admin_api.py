"""Operational account directory. Roles stay server-owned.

An operational admin may provision accounts, replace a single server role,
and disable or restore an account. Audit read is a separate right held in
this service, not a role a request body can mint. Directory and search
responses use a fixed field allowlist. They do not open case artifacts, and
they do not copy narratives, messages, evidence, keys, or summaries.

Disabling an account, or changing its role, drops that principal's current
browser session before the response returns. The next request on an
already-open client, and any forged replay of the old cookie, fails closed.
This module does not send external messages and does not use WebSocket or SSE.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from starlette.requests import Request

from applications.browser_sessions import BrowserSessionService
from applications.principal_store import (
    KNOWN_ROLES,
    PrincipalRecord,
    PrincipalStore,
    PrincipalStoreError,
)

TASK_ID = "CIMP-GUI-50"
ADMIN_PAGE_PATH = "/admin"
ADMIN_API_PREFIX = "/api/admin"
ACCOUNT_KINDS = KNOWN_ROLES
ACCOUNT_STATUSES = frozenset({"active", "disabled"})
LEAST_PRIVILEGE_FIELDS = (
    "principal_id",
    "roles",
    "status",
    "revision",
    "role_authority",
    "audit_right",
)
CONTENT_REQUEST_FIELDS = frozenset({
    "narrative",
    "narratives",
    "message",
    "messages",
    "evidence",
    "key",
    "keys",
    "summary",
    "summaries",
    "case_plaintext",
    "plaintext",
    "credential",
    "credentials",
    "data_key",
    "browser_key",
    "wrapped_ciphertext",
    "envelope",
})
REJECTED_BODY_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "membership",
    "grant",
    "actions",
    *CONTENT_REQUEST_FIELDS,
})
ADMIN_LIMITATIONS = (
    "request_body_cannot_assign_staff_role",
    "audit_right_is_separate_from_operational_admin",
    "admin_search_does_not_decrypt_case_artifacts",
    "case_content_requires_independent_case_grant",
    "disable_and_role_change_drop_existing_sessions",
    "no_external_notification_delivery",
    "no_websocket_or_sse",
)


class OperationalAdminError(Exception):
    """Fail-closed directory error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise OperationalAdminError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise OperationalAdminError(code)
    return value


class OperationalAdminService:
    """Account lifecycle over the sealed principal roster and live sessions."""

    def __init__(
        self,
        *,
        principals: PrincipalStore,
        sessions: BrowserSessionService,
        clock: Callable[[], int],
        audit_principal_ids: Sequence[str] = (),
        memberships: Any = None,
    ) -> None:
        if not isinstance(principals, PrincipalStore) or not isinstance(sessions, BrowserSessionService):
            raise OperationalAdminError("authority_owners")
        if not callable(clock):
            raise OperationalAdminError("authority_owners")
        if not isinstance(audit_principal_ids, Sequence) or isinstance(audit_principal_ids, (str, bytes)):
            raise OperationalAdminError("authority_owners")
        self._principals = principals
        self._sessions = sessions
        self._clock = clock
        self._memberships = memberships
        self._audit_readers = {str(item) for item in audit_principal_ids}
        self._events: list[dict[str, Any]] = []

    def list_accounts(self, actor_principal_id: str, session_roles: Sequence[str], query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._query(query or {})
        self._reject_content_request(payload)
        needle = payload.get("principal_id", "")
        if needle != "" and not isinstance(needle, str):
            raise OperationalAdminError("principal_id")
        case_id = payload.get("case_id", "")
        if case_id != "":
            case_id = _label(case_id, "case_id")
            if not self._independent_grant(actor.principal_id, case_id):
                raise OperationalAdminError("independent_case_grant_required")
        accounts = []
        for record in self._principals.recover():
            if needle and needle not in record.principal_id:
                continue
            accounts.append(self._least(record))
        accounts.sort(key=lambda item: item["principal_id"])
        return {
            "actor_principal_id": actor.principal_id,
            "accounts": accounts,
            "fields": list(LEAST_PRIVILEGE_FIELDS),
            "case_content": None,
            "narratives": [],
            "messages": [],
            "evidence": [],
            "keys": [],
            "summaries": [],
            "case_id": case_id or None,
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def provision(self, actor_principal_id: str, session_roles: Sequence[str], body: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        kind = _label(payload.get("account_kind"), "account_kind")
        if kind not in ACCOUNT_KINDS:
            raise OperationalAdminError("unknown_role")
        if kind == "complainant":
            created = self._principals.register_from_request({})
        else:
            created = self._principals.install_server_role(role=kind)
        self._event(actor.principal_id, "provision", created, detail=kind)
        return self._least(created)

    def change_role(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        subject_principal_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        subject_id = _label(subject_principal_id, "principal_id")
        kind = _label(payload.get("account_kind"), "account_kind")
        expected = payload.get("expected_revision")
        if type(expected) is not int:
            raise OperationalAdminError("revision_conflict")
        before = self._load(subject_id)
        if before.status != "active":
            raise OperationalAdminError("account_disabled")
        if kind not in before.roles and self._active_admin_count() == 1 and "operational_admin" in before.roles:
            raise OperationalAdminError("last_operational_admin")
        try:
            updated = self._principals.assign_role(
                actor_principal_id=actor.principal_id,
                subject_principal_id=subject_id,
                role=kind,
                expected_revision=expected,
            )
        except PrincipalStoreError as exc:
            raise OperationalAdminError(_role_code(exc.code)) from exc
        self._revoke(subject_id)
        self._event(actor.principal_id, "role_change", updated, detail=kind)
        return self._least(updated)

    def set_status(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        subject_principal_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        payload = self._body(body)
        subject_id = _label(subject_principal_id, "principal_id")
        status = _label(payload.get("status"), "status")
        if status not in ACCOUNT_STATUSES:
            raise OperationalAdminError("status")
        expected = payload.get("expected_revision")
        if type(expected) is not int:
            raise OperationalAdminError("revision_conflict")
        subject = self._load(subject_id)
        if expected != subject.revision:
            raise OperationalAdminError("revision_conflict")
        if subject.principal_id == actor.principal_id and status != "active":
            raise OperationalAdminError("actor_cannot_disable_self")
        if status == "disabled" and "operational_admin" in subject.roles and self._active_admin_count() == 1:
            raise OperationalAdminError("last_operational_admin")
        updated = PrincipalRecord(
            principal_id=subject.principal_id,
            tenant_id=subject.tenant_id,
            roles=subject.roles,
            status=status,
            revision=subject.revision + 1,
            role_authority="server",
            excluded_fields=subject.excluded_fields,
        )
        self._principals._seal(updated)
        if status != "active":
            self._audit_readers.discard(subject_id)
        self._revoke(subject_id)
        self._event(actor.principal_id, "status", updated, detail=status)
        return self._least(updated)

    def set_audit_right(
        self,
        actor_principal_id: str,
        session_roles: Sequence[str],
        subject_principal_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        if actor.principal_id not in self._audit_readers:
            raise OperationalAdminError("audit_right_required")
        payload = self._body(body)
        subject_id = _label(subject_principal_id, "principal_id")
        enabled = payload.get("enabled")
        if type(enabled) is not bool:
            raise OperationalAdminError("audit_right")
        expected = payload.get("expected_revision")
        if type(expected) is not int:
            raise OperationalAdminError("revision_conflict")
        subject = self._load(subject_id)
        if expected != subject.revision:
            raise OperationalAdminError("revision_conflict")
        if "operational_admin" not in subject.roles or subject.status != "active":
            raise OperationalAdminError("audit_right")
        if enabled:
            self._audit_readers.add(subject_id)
        else:
            if subject_id == actor.principal_id and self._audit_readers == {actor.principal_id}:
                raise OperationalAdminError("last_audit_right")
            self._audit_readers.discard(subject_id)
        self._event(actor.principal_id, "audit_right", subject, detail="granted" if enabled else "revoked")
        return self._least(subject)

    def audit_log(self, actor_principal_id: str, session_roles: Sequence[str]) -> dict[str, Any]:
        actor = self._require_admin(actor_principal_id, session_roles)
        if actor.principal_id not in self._audit_readers:
            raise OperationalAdminError("audit_right_required")
        return {
            "actor_principal_id": actor.principal_id,
            "events": list(self._events),
            "fields": ["at", "actor_principal_id", "action", "subject_principal_id", "detail", "revision"],
            "case_content": None,
            "limitations": list(ADMIN_LIMITATIONS),
        }

    def _least(self, record: PrincipalRecord) -> dict[str, Any]:
        view = {
            "principal_id": record.principal_id,
            "roles": list(record.roles),
            "status": record.status,
            "revision": record.revision,
            "role_authority": record.role_authority,
            "audit_right": record.principal_id in self._audit_readers,
        }
        if tuple(view) != LEAST_PRIVILEGE_FIELDS:
            raise OperationalAdminError("least_privilege_fields")
        return view

    def _require_admin(self, actor_principal_id: str, session_roles: Sequence[str]) -> PrincipalRecord:
        actor_id = _label(actor_principal_id, "unauthenticated")
        presented = tuple(session_roles) if isinstance(session_roles, Sequence) and not isinstance(session_roles, str) else ()
        try:
            record = self._principals.load(actor_id)
        except PrincipalStoreError as exc:
            self._revoke(actor_id)
            raise OperationalAdminError("unauthenticated") from exc
        if record.status != "active":
            self._revoke(actor_id)
            raise OperationalAdminError("account_disabled")
        if tuple(record.roles) != presented:
            self._revoke(actor_id)
            raise OperationalAdminError("authority_stale")
        if "operational_admin" not in record.roles:
            raise OperationalAdminError("action_not_permitted")
        return record

    def _load(self, principal_id: str) -> PrincipalRecord:
        try:
            return self._principals.load(principal_id)
        except PrincipalStoreError as exc:
            raise OperationalAdminError("missing_principal") from exc

    def _active_admin_count(self) -> int:
        return sum(
            1
            for record in self._principals.recover()
            if record.status == "active" and "operational_admin" in record.roles
        )

    def _independent_grant(self, actor_id: str, case_id: str) -> bool:
        memberships = self._memberships
        if memberships is None or not hasattr(memberships, "recover"):
            return False
        try:
            grants = memberships.recover()
        except Exception as exc:
            raise OperationalAdminError("independent_case_grant_required") from exc
        for grant in grants:
            if getattr(grant, "member_principal_id", None) != actor_id:
                continue
            if getattr(grant, "case_id", None) != case_id:
                continue
            if getattr(grant, "status", None) == "accepted":
                return True
        return False

    def _reject_content_request(self, payload: Mapping[str, Any]) -> None:
        if any(name in payload for name in CONTENT_REQUEST_FIELDS):
            raise OperationalAdminError("admin_case_content_denied")

    def _body(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise OperationalAdminError("request_body")
        self._reject_content_request(body)
        if any(name in body for name in REJECTED_BODY_FIELDS):
            raise OperationalAdminError("request_cannot_mint_authority")
        return body

    def _query(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(query, Mapping):
            raise OperationalAdminError("request_body")
        return query

    def _event(self, actor_id: str, action: str, subject: PrincipalRecord, *, detail: str) -> None:
        self._events.append({
            "at": self._now(),
            "actor_principal_id": actor_id,
            "action": action,
            "subject_principal_id": subject.principal_id,
            "detail": detail,
            "revision": subject.revision,
        })

    def _revoke(self, principal_id: str) -> None:
        sessions = self._sessions
        records = getattr(sessions, "_records", None)
        by_principal = getattr(sessions, "_by_principal", None)
        drop = getattr(sessions, "_drop", None)
        if not isinstance(records, dict) or not callable(drop):
            return
        doomed = [session_id for session_id, record in list(records.items()) if record.principal_id == principal_id]
        if isinstance(by_principal, dict):
            current = by_principal.get(principal_id)
            if isinstance(current, str) and current not in doomed:
                doomed.append(current)
        for session_id in doomed:
            drop(session_id)

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise OperationalAdminError("clock")
        return value


def _role_code(code: str) -> str:
    if code in {"actor_lacks_role_authority", "actor_cannot_drop_own_staff_role", "unknown_role", "revision_conflict", "missing_principal"}:
        return code
    return "action_not_permitted"


def admin_http_status(code: str) -> int:
    if code in {"unauthenticated", "account_disabled", "authority_stale", "request_body"}:
        return 401
    if code == "revision_conflict":
        return 409
    if code == "admin_unavailable":
        return 503
    if code == "missing_principal":
        return 404
    return 403


def mount_operational_admin(app: Any) -> None:
    """Mount the directory page and API. Session checks run in case route composition."""

    from fastapi.responses import HTMLResponse, JSONResponse

    root_page = __import__("pathlib").Path(__file__).resolve().parent.parent / "templates" / "admin.html"

    def _service(request: Any) -> OperationalAdminService:
        service = getattr(request.app.state, "operational_admin", None)
        if not isinstance(service, OperationalAdminService):
            raise OperationalAdminError("admin_unavailable")
        return service

    def _actor(request: Any) -> tuple[str, tuple[str, ...]]:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        roles = getattr(principal, "roles", None)
        if not isinstance(actor, str) or actor == "" or not isinstance(roles, tuple):
            raise OperationalAdminError("unauthenticated")
        return actor, roles

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "admin_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: OperationalAdminError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=admin_http_status(exc.code))

    @app.get(ADMIN_PAGE_PATH)
    async def admin_page():
        html = root_page.read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"cache-control": "no-store"})

    @app.get(ADMIN_API_PREFIX + "/accounts")
    async def admin_accounts(request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).list_accounts(actor, roles, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/accounts")
    async def admin_provision(request: Request):
        try:
            actor, roles = _actor(request)
            created = _service(request).provision(actor, roles, _material(request))
        except OperationalAdminError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.post(ADMIN_API_PREFIX + "/accounts/{principal_id}/role")
    async def admin_role(principal_id: str, request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).change_role(actor, roles, principal_id, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/accounts/{principal_id}/status")
    async def admin_status(principal_id: str, request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).set_status(actor, roles, principal_id, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.post(ADMIN_API_PREFIX + "/accounts/{principal_id}/audit")
    async def admin_audit_right(principal_id: str, request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).set_audit_right(actor, roles, principal_id, _material(request)))
        except OperationalAdminError as exc:
            return _fail(exc)

    @app.get(ADMIN_API_PREFIX + "/audit")
    async def admin_audit(request: Request):
        try:
            actor, roles = _actor(request)
            return JSONResponse(_service(request).audit_log(actor, roles))
        except OperationalAdminError as exc:
            return _fail(exc)
