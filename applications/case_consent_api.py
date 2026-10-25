"""Persist case-specific processing consent.

Each case starts local-private. Grok processing is allowed only after the case
owner explicitly authorizes one purpose. Revocation returns that purpose to
local-private and bumps the consent generation so a late result cannot reuse
the earlier choice.

Lawyer membership, an operational-admin role, development Grok authorization,
and receipt of a message do not create or imply egress consent. This module
does not call a model and does not claim WebSocket or SSE.
"""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
from pathlib import Path
from typing import Any, Callable, Mapping

from starlette.requests import Request

from applications.case_directory import CaseDirectory, CaseDirectoryError
from integrations.ipfs_datasets.llm import (
    OPERATION_CONSENT_CONTRACT,
    OPERATION_CONSENT_VERSION,
    PRIVACY_GROK_MODEL,
    PRIVACY_GROK_PROVIDER,
    PRIVACY_PROCESSING_GROK,
    PRIVACY_PROCESSING_LOCAL,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateStorageError,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-33"
CONSENT_KIND = "case_processing_consent"
CONSENT_REVISION = "current"
CONSENT_CONTRACT = "case_processing_consent"
CONSENT_VERSION = "1"
MODES = (PRIVACY_PROCESSING_LOCAL, PRIVACY_PROCESSING_GROK)
PURPOSE_DATA_CLASS = {
    "extract_facts": "raw_intake",
    "propose_questions": "raw_intake",
    "explain_candidate": "raw_intake",
    "citation_acquisition": "public_legal_source_graph",
    "public_law_citation": "public_legal_source_graph",
}
IMPLICATIONS = (
    "lawyer_membership",
    "admin_role",
    "development_grok_authorization",
    "message_receipt",
)
_IMPLIED_FIELDS = frozenset({
    "lawyer_membership",
    "admin_role",
    "development_grok_authorization",
    "development_grok_authorized",
    "message_receipt",
    "message_received",
    "is_admin",
    "is_lawyer",
    "is_member",
    "membership",
    "role",
    "roles",
    "staff_role",
    "trusted_local",
    "trust",
})
LIMITATIONS = (
    "default_is_local_private",
    "grok_requires_explicit_case_purpose",
    "lawyer_membership_does_not_imply_egress",
    "admin_role_does_not_imply_egress",
    "development_grok_authorization_does_not_imply_egress",
    "message_receipt_does_not_imply_egress",
    "revocation_bumps_generation",
    "no_model_dispatch",
    "no_websocket_or_sse",
)


class CaseConsentError(Exception):
    """Fail-closed consent error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def consent_http_status(code: str) -> int:
    if code in {"missing_case", "missing_purpose"}:
        return 404
    if code in {"revision_conflict"}:
        return 409
    if code in {"unauthenticated", "request_body"}:
        return 401
    if code == "consent_unavailable":
        return 503
    return 403


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseConsentError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseConsentError(code)
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise CaseConsentError("revision_conflict")
    return value


def _blank_decision(purpose: str) -> dict[str, Any]:
    return {
        "purpose": purpose,
        "data_class": PURPOSE_DATA_CLASS[purpose],
        "mode": PRIVACY_PROCESSING_LOCAL,
        "explicit": False,
        "revoked": False,
        "provider": "",
        "model": "",
        "generation": 0,
    }


def _display(decision: Mapping[str, Any]) -> str:
    if decision.get("revoked") is True or (
        decision.get("mode") == PRIVACY_PROCESSING_LOCAL and int(decision.get("generation") or 0) > 0 and decision.get("explicit") is not True
    ):
        if decision.get("revoked") is True:
            return (
                "Revoked: Grok processing for this purpose is not authorized. "
                "Processing is local private."
            )
    if decision.get("mode") == PRIVACY_PROCESSING_GROK and decision.get("explicit") is True and decision.get("revoked") is not True:
        return (
            "Explicitly authorized Grok processing: grok_cli / grok-4.7 for this case and purpose."
        )
    return "Local private: this purpose never calls a remote provider."


def _egress(decision: Mapping[str, Any]) -> bool:
    return (
        decision.get("mode") == PRIVACY_PROCESSING_GROK
        and decision.get("explicit") is True
        and decision.get("revoked") is not True
        and decision.get("provider") == PRIVACY_GROK_PROVIDER
        and decision.get("model") == PRIVACY_GROK_MODEL
    )


class CaseConsentService:
    """Owner-only persisted processing choices, one record per case."""

    def __init__(self, root: str | Path, *, cases: CaseDirectory, key: bytes, key_id: str, clock: Callable[[], int]) -> None:
        if not isinstance(cases, CaseDirectory):
            raise CaseConsentError("authority_owners")
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseConsentError("key_material")
        if not callable(clock):
            raise CaseConsentError("authority_owners")
        self._cases = cases
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._clock = clock
        self._root = Path(root)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def read(self, actor_principal_id: str, case_id: str) -> dict[str, Any]:
        record = self._owned(actor_principal_id, case_id)
        stored = self._load(record)
        return self._view(record, stored)

    def choose(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        material = self._body(body)
        self._reject_implications(material)
        purpose = _label(material.get("purpose"), "missing_purpose")
        if purpose not in PURPOSE_DATA_CLASS:
            raise CaseConsentError("missing_purpose")
        mode = _label(material.get("mode"), "mode_required")
        if mode not in MODES:
            raise CaseConsentError("mode_required")
        expected = _generation(material.get("expected_generation"))
        explicit = material.get("explicit_case_purpose") is True
        if mode == PRIVACY_PROCESSING_GROK and not explicit:
            raise CaseConsentError("explicit_case_purpose_required")
        if mode == PRIVACY_PROCESSING_LOCAL and explicit:
            raise CaseConsentError("explicit_case_purpose_required")
        record = self._owned(actor_principal_id, case_id)
        with self._lock():
            stored = self._load(record)
            current = int(stored["generation"])
            if expected != current:
                raise CaseConsentError("revision_conflict")
            generation = current + 1
            decisions = {key: dict(value) for key, value in stored["decisions"].items()}
            decision = dict(decisions[purpose])
            decision["generation"] = generation
            decision["data_class"] = PURPOSE_DATA_CLASS[purpose]
            if mode == PRIVACY_PROCESSING_GROK:
                decision.update({
                    "mode": PRIVACY_PROCESSING_GROK,
                    "explicit": True,
                    "revoked": False,
                    "provider": PRIVACY_GROK_PROVIDER,
                    "model": PRIVACY_GROK_MODEL,
                })
            else:
                decision.update({
                    "mode": PRIVACY_PROCESSING_LOCAL,
                    "explicit": False,
                    "revoked": current > 0 and decisions[purpose].get("mode") == PRIVACY_PROCESSING_GROK,
                    "provider": "",
                    "model": "",
                })
            decisions[purpose] = decision
            stored = {
                "contract": CONSENT_CONTRACT,
                "version": CONSENT_VERSION,
                "tenant_id": record.tenant_id,
                "case_id": record.case_id,
                "owner_principal_id": record.owner_principal_id,
                "generation": generation,
                "decided_at": self._now(),
                "decisions": decisions,
            }
            self._write(record, stored)
        return self._view(record, stored)

    def revoke(self, actor_principal_id: str, case_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        material = self._body(body)
        self._reject_implications(material)
        purpose = _label(material.get("purpose"), "missing_purpose")
        if purpose not in PURPOSE_DATA_CLASS:
            raise CaseConsentError("missing_purpose")
        material = dict(material)
        material["mode"] = PRIVACY_PROCESSING_LOCAL
        material.pop("explicit_case_purpose", None)
        return self.choose(actor_principal_id, case_id, material)

    def _owned(self, actor_principal_id: str, case_id: str):
        actor = _label(actor_principal_id, "unauthenticated")
        try:
            record = self._cases.select_case(actor_principal_id=actor, case_id=case_id)
        except CaseDirectoryError as exc:
            code = "missing_case" if exc.code in {"missing_case", "case_id", "user_id_not_a_selector"} else exc.code
            raise CaseConsentError(code) from exc
        if record.owner_principal_id != actor:
            raise CaseConsentError("missing_case")
        return record

    def _body(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise CaseConsentError("request_body")
        return body

    def _reject_implications(self, body: Mapping[str, Any]) -> None:
        if any(name in body for name in _IMPLIED_FIELDS):
            raise CaseConsentError("consent_not_implied")

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or isinstance(value, bool):
            raise CaseConsentError("clock")
        return value

    def _path(self, record) -> Path:
        identity = json.dumps([record.tenant_id, record.case_id, record.resource_id], separators=(",", ":"))
        return self._root / hashlib.sha256(identity.encode()).hexdigest()

    def _binding(self, record) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=record.tenant_id,
            case_id=record.case_id,
            artifact_kind=CONSENT_KIND,
            revision=CONSENT_REVISION,
            principal_id=record.owner_principal_id,
        )

    def _empty(self, record) -> dict[str, Any]:
        return {
            "contract": CONSENT_CONTRACT,
            "version": CONSENT_VERSION,
            "tenant_id": record.tenant_id,
            "case_id": record.case_id,
            "owner_principal_id": record.owner_principal_id,
            "generation": 0,
            "decided_at": 0,
            "decisions": {purpose: _blank_decision(purpose) for purpose in PURPOSE_DATA_CLASS},
        }

    def _load(self, record) -> dict[str, Any]:
        path = self._path(record)
        if not path.is_file():
            return self._empty(record)
        try:
            plaintext = open_private_artifact(
                path.read_bytes(),
                binding=self._binding(record),
                key=self._key,
                expected_key_id=self._key_id,
            )
            document = json.loads(plaintext.decode("utf-8"))
        except (PrivateArtifactIntegrityError, PrivateStorageError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CaseConsentError("consent_unavailable") from exc
        if not isinstance(document, dict) or document.get("case_id") != record.case_id:
            raise CaseConsentError("consent_unavailable")
        if document.get("tenant_id") != record.tenant_id or document.get("owner_principal_id") != record.owner_principal_id:
            raise CaseConsentError("consent_unavailable")
        decisions = document.get("decisions")
        if not isinstance(decisions, dict) or set(decisions) != set(PURPOSE_DATA_CLASS):
            raise CaseConsentError("consent_unavailable")
        document["generation"] = _generation(document.get("generation"))
        return document

    def _write(self, record, document: dict[str, Any]) -> None:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=self._binding(record), key=self._key, key_id=self._key_id)
        path = self._path(record)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(envelope)
        os.replace(temporary, path)

    def _lock(self):
        class _Guard:
            def __init__(self, root: Path) -> None:
                self._fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR, 0o600)

            def __enter__(self):
                fcntl.flock(self._fd, fcntl.LOCK_EX)
                return self

            def __exit__(self, *_args):
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)

        return _Guard(self._root)

    def _view(self, record, stored: Mapping[str, Any]) -> dict[str, Any]:
        decisions = []
        grants = []
        for purpose in PURPOSE_DATA_CLASS:
            raw = dict(stored["decisions"][purpose])
            item = {
                "purpose": purpose,
                "data_class": PURPOSE_DATA_CLASS[purpose],
                "mode": raw.get("mode") if raw.get("mode") in MODES else PRIVACY_PROCESSING_LOCAL,
                "explicit": raw.get("explicit") is True and raw.get("mode") == PRIVACY_PROCESSING_GROK and raw.get("revoked") is not True,
                "revoked": raw.get("revoked") is True,
                "provider": PRIVACY_GROK_PROVIDER if _egress(raw) else "",
                "model": PRIVACY_GROK_MODEL if _egress(raw) else "",
                "generation": int(raw.get("generation") or 0),
                "egress_authorized": _egress(raw),
                "display": _display(raw),
            }
            decisions.append(item)
            if item["egress_authorized"]:
                grants.append({
                    "purpose": purpose,
                    "provider_kind": "grok_inference",
                    "provider": PRIVACY_GROK_PROVIDER,
                    "model": PRIVACY_GROK_MODEL,
                    "data_class": item["data_class"],
                    "explicit": True,
                    "tools": False,
                })
        return {
            "task_id": TASK_ID,
            "case_id": record.case_id,
            "tenant_id": record.tenant_id,
            "owner_principal_id": record.owner_principal_id,
            "generation": int(stored["generation"]),
            "processing_choices": list(MODES),
            "decisions": decisions,
            "egress_authorized": any(item["egress_authorized"] for item in decisions),
            "implications": {name: False for name in IMPLICATIONS},
            "operation_consent": {
                "contract": OPERATION_CONSENT_CONTRACT,
                "version": OPERATION_CONSENT_VERSION,
                "user_id": record.owner_principal_id,
                "case_id": record.case_id,
                "generation": int(stored["generation"]),
                "revoked": not grants,
                "grants": grants,
            },
            "limitations": list(LIMITATIONS),
        }


def mount_case_consent(app: Any) -> None:
    """Mount consent routes. Catalog authentication runs before these handlers."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseConsentService:
        service = getattr(request.app.state, "case_consent", None)
        if not isinstance(service, CaseConsentService):
            raise CaseConsentError("consent_unavailable")
        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseConsentError("unauthenticated")
        return actor

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: CaseConsentError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=consent_http_status(exc.code))

    @app.get("/api/cases/{case_id}/processing-consent")
    async def consent_read(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).read(_actor(request), case_id))
        except CaseConsentError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/processing-consent")
    async def consent_choose(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).choose(_actor(request), case_id, _material(request)))
        except CaseConsentError as exc:
            return _fail(exc)

    @app.post("/api/cases/{case_id}/processing-consent/revoke")
    async def consent_revoke(case_id: str, request: Request):
        try:
            return JSONResponse(_service(request).revoke(_actor(request), case_id, _material(request)))
        except CaseConsentError as exc:
            return _fail(exc)
