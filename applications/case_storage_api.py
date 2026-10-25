"""Case ciphertext durability through Kit manifest, queue, pin, and readback.

The browser session supplies the actor. A body cannot mint authority, choose a
public gateway, or declare durability from a CID. Plaintext is sealed before
the Kit owner sees it. The response lists local commit, queued replication,
pin, and verified replica as separate states and sets durable only after
ciphertext readback matches.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE
from applications.case_directory import CaseDirectory, CaseDirectoryError

from integrations.private_storage import (
    DURABILITY_STATES,
    CiphertextDurabilityError,
    PrivateArtifactBinding,
    UserOwnedKeySession,
    seal_private_artifact,
    verify_ciphertext_durability,
)

TASK_ID = "CIMP-GUI-38"
_KIND = "case-ciphertext"
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}
_REJECTED_FIELDS = frozenset({
    "cid",
    "content_cid",
    "url",
    "uri",
    "gateway",
    "public_gateway",
    "infer_from_cid",
    "durable",
    "role",
    "trusted_local",
    "browser_key",
    "key",
    "data_key",
})


class CaseStorageError(Exception):
    def __init__(self, code: str, receipt: Mapping[str, Any] | None = None) -> None:
        self.code = code
        self.receipt = dict(receipt) if isinstance(receipt, Mapping) else None
        super().__init__(code)


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseStorageError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseStorageError(code)
    if len(value) > 200:
        raise CaseStorageError(code)
    return value


def case_storage_status(code: str) -> int:
    if code in {"unauthenticated"}:
        return 401
    if code in {"not_owner", "missing_case", "key_unavailable"}:
        return 403
    if code in {"readback_mismatch", "public_gateway_rejected", "resource_mismatch", "tenant_mismatch", "replay_mismatch"}:
        return 409
    if code.startswith("kit_") or code in {"kit_contracts_unavailable", "storage_unavailable"}:
        return 503
    return 400


class CaseStorageService:
    """Owner-only durability checks for one sealed case payload."""

    def __init__(self, directory: CaseDirectory, sessions: Mapping[str, UserOwnedKeySession], kit: Any) -> None:
        if not isinstance(directory, CaseDirectory) or kit is None:
            raise CaseStorageError("storage_unavailable")
        self._directory = directory
        self._sessions = dict(sessions)
        self._kit = kit
        self._receipts: dict[str, dict[str, Any]] = {}
        self._identities: dict[str, dict[str, str]] = {}

    def commit(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        identity = self._identity(actor_principal_id, body)
        key_name = identity["idempotency_key"]
        previous = self._receipts.get(key_name)
        if previous is not None:
            if self._identities.get(key_name) != identity:
                raise CaseStorageError("replay_mismatch")
            return dict(previous)
        case = self._case(identity)
        session = self._sessions.get(identity["actor_principal_id"])
        if not isinstance(session, UserOwnedKeySession):
            raise CaseStorageError("key_unavailable")
        key_id = session.ensure_data_key(case.tenant_id, case.case_id)
        data_key = session.lookup_data_key(case.tenant_id, case.case_id, key_id)
        if data_key is None:
            raise CaseStorageError("key_unavailable")
        binding = PrivateArtifactBinding(
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind=_KIND,
            revision=identity["revision"],
            principal_id=case.tenant_id,
        )
        envelope = seal_private_artifact(self._content(body), binding=binding, key=data_key, key_id=key_id)
        try:
            checked = verify_ciphertext_durability(self._kit, envelope)
        except CiphertextDurabilityError as exc:
            raise CaseStorageError(exc.code) from exc
        if checked["readback_matched"] is not True:
            failed = dict(checked)
            failed["task_id"] = TASK_ID
            failed["actor_principal_id"] = identity["actor_principal_id"]
            failed["canonical_owner_principal_id"] = case.tenant_id
            failed["actor_is_encrypted_owner"] = False
            failed["durable"] = False
            raise CaseStorageError("readback_mismatch", failed)
        receipt = self._public(checked, identity, case.tenant_id)
        self._remember(key_name, identity, receipt)
        return receipt

    def read(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        identity = self._identity(actor_principal_id, body, content=False)
        self._case(identity)
        found = self._receipts.get(identity["idempotency_key"])
        if found is None or self._identities.get(identity["idempotency_key"]) != identity:
            raise CaseStorageError("missing_receipt")
        return dict(found)

    def _remember(self, key_name: str, identity: Mapping[str, str], receipt: Mapping[str, Any]) -> None:
        self._identities[key_name] = dict(identity)
        self._receipts[key_name] = dict(receipt)

    def _public(self, checked: Mapping[str, Any], identity: Mapping[str, str], canonical: str) -> dict[str, Any]:
        names = list(checked["state_names"])
        if names != list(DURABILITY_STATES) or checked["durable"] is not True:
            raise CaseStorageError(str(checked.get("code") or "readback_mismatch"))
        return {
            "task_id": TASK_ID,
            "tenant_id": identity["tenant_id"],
            "case_id": identity["case_id"],
            "resource_id": identity["resource_id"],
            "revision": identity["revision"],
            "actor_principal_id": identity["actor_principal_id"],
            "canonical_owner_principal_id": canonical,
            "actor_is_encrypted_owner": False,
            "idempotency_key": identity["idempotency_key"],
            "states": list(checked["states"]),
            "state_names": names,
            "durable": True,
            "readback_matched": True,
            "ciphertext_sha256": checked["ciphertext_sha256"],
            "byte_length": checked["byte_length"],
            "ref": checked["ref"],
            "public_gateway_consulted": False,
            "cid_inference": False,
            "pin_is_durable": False,
            "queued_replication_is_durable": False,
            "local_commit_is_durable": False,
            "limitations": (
                "durable_only_after_ciphertext_readback",
                "pin_queue_and_local_commit_are_distinct",
                "no_public_gateway_or_cid_inference",
                "no_websocket_or_sse",
            ),
        }

    def _case(self, identity: Mapping[str, str]):
        try:
            case = self._directory.select_case(actor_principal_id=identity["actor_principal_id"], case_id=identity["case_id"])
        except CaseDirectoryError as exc:
            raise CaseStorageError("not_owner") from exc
        if case.tenant_id != identity["tenant_id"]:
            raise CaseStorageError("tenant_mismatch")
        if case.resource_id != identity["resource_id"]:
            raise CaseStorageError("resource_mismatch")
        return case

    def _identity(self, actor: str, body: Mapping[str, Any], *, content: bool = True) -> dict[str, str]:
        if not isinstance(body, Mapping):
            raise CaseStorageError("request_body")
        if any(name in body for name in _REJECTED_FIELDS):
            raise CaseStorageError("selector_rejected")
        if content and "content_base64" not in body:
            raise CaseStorageError("content_rejected")
        required = ("tenant_id", "case_id", "resource_id", "revision", "idempotency_key")
        identity = {"actor_principal_id": _label(actor, "actor")}
        for name in required:
            identity[name] = _label(body.get(name), name)
        return identity

    def _content(self, body: Mapping[str, Any]) -> bytes:
        encoded = body.get("content_base64")
        if not isinstance(encoded, str) or encoded.strip() == "":
            raise CaseStorageError("content_rejected")
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise CaseStorageError("content_rejected") from exc
        if not payload or len(payload) > 256 * 1024:
            raise CaseStorageError("content_rejected")
        return payload


def mount_case_storage(app: Any) -> None:
    """Mount durability routes on the authenticated case catalog boundary."""

    from fastapi.responses import JSONResponse

    def _service(request: Request) -> CaseStorageService:
        service = getattr(request.app.state, "case_storage", None)
        if not isinstance(service, CaseStorageService):
            raise CaseStorageError("storage_unavailable")
        return service

    def _actor(request: Request) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseStorageError("unauthenticated")
        return actor

    def _verify(request: Request):
        sessions = getattr(request.app.state, "browser_sessions", None)
        bound = getattr(request.state, "browser_principal", None)
        token = request.cookies.get(SESSION_COOKIE)
        if not isinstance(sessions, BrowserSessionService) or bound is None:
            raise CaseStorageError("unauthenticated")

        def verify() -> None:
            try:
                current = sessions.authenticate_token(token)
            except BrowserSessionError as exc:
                raise CaseStorageError("unauthenticated") from exc
            if (current.principal_id != bound.principal_id or current.tenant_id != bound.tenant_id
                    or current.generation != bound.generation):
                raise CaseStorageError("unauthenticated")

        return verify

    def _material(request: Request) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, Mapping) else {}

    def _fail(exc: BaseException) -> JSONResponse:
        code = getattr(exc, "code", "storage_unavailable")
        body: dict[str, Any] = {"error": code, "durable": False}
        receipt = getattr(exc, "receipt", None)
        if isinstance(receipt, Mapping):
            body["state_names"] = list(receipt.get("state_names") or [])
            body["states"] = list(receipt.get("states") or [])
            body["readback_matched"] = receipt.get("readback_matched") is True
            body["public_gateway_consulted"] = False
            body["cid_inference"] = False
        return JSONResponse(body, status_code=case_storage_status(str(code)), headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/storage/durability")
    async def storage_commit(request: Request):
        try:
            verify = _verify(request)
            verify()
            receipt = await run_in_threadpool(_service(request).commit, _actor(request), _material(request))
            verify()
        except CaseStorageError as exc:
            return _fail(exc)
        return JSONResponse(receipt, status_code=201, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/storage/durability")
    async def storage_read(request: Request):
        try:
            verify = _verify(request)
            verify()
            receipt = await run_in_threadpool(_service(request).read, _actor(request), _material(request))
            verify()
        except CaseStorageError as exc:
            return _fail(exc)
        return JSONResponse(receipt, headers=_NO_STORE_HEADERS)
