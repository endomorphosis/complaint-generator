"""Case-scoped encrypted evidence catalog and ingestion lifecycle.

Artifacts are sealed with the case data key before any byte store sees them.
The public identifier is an opaque evidence id plus an HMAC scope binding over
the canonical tenant, case, and acting principal. A storage receipt records
ciphertext readback only. It does not establish authenticity, relevance,
admissibility, or claim support.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from applications.case_directory import CaseDirectory, CaseDirectoryError, CaseNamespace

from integrations.private_storage import (
    PrivateStorageError,
    KitLocalCiphertextBackend,
    PrivateArtifactBinding,
    UserOwnedKeySession,
    retrieve_private_artifact,
    store_private_artifact,
)

TASK_ID = "CIMP-UX-13"
INGESTION_STATUSES = (
    "received",
    "extracted",
    "needs-review",
    "linked",
    "failed",
    "unavailable",
)
LEGAL_QUALITIES = ("authenticity", "relevance", "admissibility", "claim_support")
_KIND_CATALOG = "evidence-catalog"
_KIND_ARTIFACT = "evidence-artifact"
_MAX_BYTES = 256 * 1024


class EvidenceWorkspaceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_qualities() -> dict[str, str]:
    """Receipt and ingestion never establish these legal qualities."""

    return {name: "not_established" for name in LEGAL_QUALITIES}


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise EvidenceWorkspaceError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise EvidenceWorkspaceError(code)
    if len(value) > 180:
        raise EvidenceWorkspaceError(code)
    return value


def _media(value: Any) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise EvidenceWorkspaceError("media_type")
    if any(char in value for char in ("\x00", "\n", "\r", "\\")):
        raise EvidenceWorkspaceError("media_type")
    if len(value) > 120 or value.count("/") != 1:
        raise EvidenceWorkspaceError("media_type")
    return value


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _scope_binding(*, key: bytes, tenant_id: str, case_id: str, actor: str, evidence_id: str) -> str:
    material = "\n".join((tenant_id, case_id, actor, evidence_id)).encode("utf-8")
    return hmac.new(key, material, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class _Access:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class _KeyScope:
    identity: Mapping[str, str]
    case: CaseNamespace
    session: UserOwnedKeySession
    epoch: int
    key_id: str
    data_key: bytes = field(repr=False)
    verify_request: Callable[[], None] | None = field(default=None, repr=False, compare=False)


class MemoryByteBackend:
    """Process-local ciphertext store. Callers pass already sealed envelopes."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def add(self, data: bytes, pin: bool = True) -> dict[str, Any]:
        cid = "evcid-" + hashlib.sha256(bytes(data)).hexdigest()
        self._blobs[cid] = bytes(data)
        return {"cid": cid, "status": "available", "pinned": bool(pin)}

    def cat(self, cid: str) -> bytes:
        found = self._blobs.get(cid)
        if found is None:
            raise EvidenceWorkspaceError("ciphertext_unavailable")
        return found

    def contains(self, needle: bytes) -> bool:
        return any(needle in blob for blob in self._blobs.values())


class EvidenceWorkspace:
    """Authorized catalog of one actor's evidence inside one owned case."""

    def __init__(self, directory: CaseDirectory, sessions: Mapping[str, UserOwnedKeySession], backend: Any, root: Path) -> None:
        if not isinstance(directory, CaseDirectory) or backend is None:
            raise EvidenceWorkspaceError("evidence_unavailable")
        self._directory = directory
        self._sessions = dict(sessions)
        self._backend = backend
        self._backend_name = KitLocalCiphertextBackend.backend_name if type(backend) is KitLocalCiphertextBackend else "evidence-memory"
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock = threading.RLock()

    def receive(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        identity = self._identity(actor, body)
        content = self._content(body.get("content_base64"), "content_rejected")
        source = _label(body.get("source_filename"), "source_filename")
        original = _label(body.get("original_filename"), "original_filename")
        media = _media(body.get("media_type") or "application/octet-stream")
        self._reject_legal_claims(body)
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            prior = document["idempotency"].get(identity["idempotency_key"])
            if prior is not None:
                item = document["items"].get(prior)
                if item is None or item.get("integrity_sha256") != _digest(content) or item.get("source_filename") != source:
                    raise EvidenceWorkspaceError("replay_mismatch")
                self._verify_scope(scope)
                return self._project(item, verified=True)
            evidence_id = "ev-" + hashlib.sha256(os.urandom(32)).hexdigest()[:32]
            version = self._seal_version(
                identity, case, key_id, data_key, evidence_id, 1, "source", content, scope,
            )
            item = {
                "evidence_id": evidence_id,
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": identity["resource_id"],
                "actor_principal_id": identity["actor_principal_id"],
                "canonical_owner_principal_id": case.tenant_id,
                "actor_is_canonical_owner": identity["actor_principal_id"] == case.tenant_id,
                "source_filename": source,
                "original_filename": original,
                "media_type": media,
                "ingestion_status": "received",
                "prior_ingestion_status": "",
                "artifact_versions": [version],
                "current_version": 1,
                "integrity_sha256": version["integrity_sha256"],
                "scope_binding": _scope_binding(
                    key=data_key, tenant_id=case.tenant_id, case_id=case.case_id,
                    actor=identity["actor_principal_id"], evidence_id=evidence_id,
                ),
                "complaint_link_id": "",
                "failure_code": "",
                "legal": legal_qualities(),
                "receipt": self._receipt(version),
            }
            document["items"][evidence_id] = item
            document["idempotency"][identity["idempotency_key"]] = evidence_id
            self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            return self._project(item, verified=True)

    def transition(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        identity = self._identity(actor, body, content=False)
        evidence_id = _label(body.get("evidence_id"), "evidence_id")
        action = _label(body.get("action"), "action")
        self._reject_legal_claims(body)
        with self._lock:
            scope = self._open(identity, verify_request=verify_request)
            case, key_id, data_key = scope.case, scope.key_id, scope.data_key
            document = self._load(identity, case, key_id, data_key, scope)
            item = document["items"].get(evidence_id)
            if item is None or item.get("actor_principal_id") != identity["actor_principal_id"]:
                raise EvidenceWorkspaceError("missing_evidence")
            expected = body.get("expected_artifact_version")
            if type(expected) is not int or expected != item["current_version"]:
                raise EvidenceWorkspaceError("revision_conflict")
            if action == "extract":
                self._extract(identity, case, key_id, data_key, item, body, scope)
            elif action == "needs-review":
                if item["ingestion_status"] not in {"received", "extracted"}:
                    raise EvidenceWorkspaceError("lifecycle_conflict")
                self._move(item, "needs-review")
            elif action == "link":
                if item["ingestion_status"] not in {"extracted", "needs-review"}:
                    raise EvidenceWorkspaceError("lifecycle_conflict")
                item["complaint_link_id"] = _label(body.get("complaint_link_id"), "complaint_link_id")
                self._move(item, "linked")
            elif action == "fail":
                item["failure_code"] = _label(body.get("failure_code"), "failure_code")
                self._move(item, "failed")
            else:
                raise EvidenceWorkspaceError("action")
            item["legal"] = legal_qualities()
            self._save(identity, case, key_id, data_key, document, scope)
            self._verify_scope(scope)
            return self._project(item, verified=item["ingestion_status"] != "unavailable")

    def list_catalog(self, actor: str, body: Mapping[str, Any], *, verify_request: Callable[[], None] | None = None) -> dict[str, Any]:
        identity = self._identity(actor, body, content=False, idempotency=False)
        with self._lock:
            try:
                scope = self._open(identity, verify_request=verify_request)
                case, key_id, data_key = scope.case, scope.key_id, scope.data_key
                document = self._load(identity, case, key_id, data_key, scope)
            except EvidenceWorkspaceError as exc:
                if exc.code in {"key_unavailable", "ciphertext_unavailable", "evidence_unavailable"}:
                    return {
                        "task_id": TASK_ID,
                        "ingestion_status": "unavailable",
                        "items": [],
                        "legal": legal_qualities(),
                        "receipt_establishes_legal_quality": False,
                        "error": exc.code,
                    }
                raise
            items = []
            for item in document["items"].values():
                if item.get("actor_principal_id") != identity["actor_principal_id"]:
                    continue
                items.append(self._observe(identity, case, key_id, data_key, item, scope))
            self._verify_scope(scope)
            return {
                "task_id": TASK_ID,
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "actor_principal_id": identity["actor_principal_id"],
                "canonical_owner_principal_id": case.tenant_id,
                "ingestion_status": "" if not items else "catalog",
                "catalog_empty": not items,
                "items": items,
                "legal": legal_qualities(),
                "receipt_establishes_legal_quality": False,
            }

    def _extract(self, identity, case, key_id, data_key, item, body, scope) -> None:
        encoded = body.get("extracted_content_base64")
        if not isinstance(encoded, str) or encoded == "":
            item["failure_code"] = "extraction_capability_unavailable"
            self._move(item, "unavailable")
            return
        try:
            content = self._content(encoded, "content_rejected")
        except EvidenceWorkspaceError:
            item["failure_code"] = "extraction_failed"
            self._move(item, "failed")
            return
        claimed = body.get("expected_integrity_sha256")
        actual = _digest(content)
        if isinstance(claimed, str) and claimed != actual:
            item["failure_code"] = "integrity_mismatch"
            self._move(item, "failed")
            return
        if item["ingestion_status"] not in {"received", "needs-review"}:
            raise EvidenceWorkspaceError("lifecycle_conflict")
        version_number = item["current_version"] + 1
        version = self._seal_version(
            identity, case, key_id, data_key, item["evidence_id"], version_number, "extraction", content, scope,
        )
        item["artifact_versions"].append(version)
        item["current_version"] = version_number
        item["integrity_sha256"] = actual
        item["failure_code"] = ""
        self._move(item, "extracted")
        item["receipt"] = self._receipt(version)

    def _move(self, item: dict[str, Any], status: str) -> None:
        if status not in INGESTION_STATUSES:
            raise EvidenceWorkspaceError("lifecycle_conflict")
        item["prior_ingestion_status"] = item["ingestion_status"]
        item["ingestion_status"] = status

    def _seal_version(self, identity, case, key_id, data_key, evidence_id, number, kind, content, scope) -> dict[str, Any]:
        access = _Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id)
        revision = f"{evidence_id}-v{number}"
        try:
            stored = store_private_artifact(
                content,
                access=access,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind=_KIND_ARTIFACT,
                revision=revision,
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=self._backend,
                backend_name=self._backend_name,
                pin_content=False,
            )
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("evidence_unavailable") from exc
        self._verify_scope(scope)
        return {
            "version": number,
            "kind": kind,
            "integrity_sha256": _digest(content),
            "byte_length": len(content),
            "ciphertext_cid": str(stored.get("cid") or ""),
            "key_id": key_id,
            "ciphertext_readback": stored.get("verified") is True,
        }

    def _observe(self, identity, case, key_id, data_key, item, scope) -> dict[str, Any]:
        current = item["artifact_versions"][-1]
        verified = False
        try:
            opened = retrieve_private_artifact(
                current["ciphertext_cid"],
                access=_Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind=_KIND_ARTIFACT,
                revision=f"{item['evidence_id']}-v{current['version']}",
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=self._backend,
                backend_name=self._backend_name,
            )
            payload = opened.get("data")
            verified = isinstance(payload, (bytes, bytearray)) and _digest(bytes(payload)) == current["integrity_sha256"]
        except (PrivateStorageError, EvidenceWorkspaceError):
            verified = False
        self._verify_scope(scope)
        expected_scope = _scope_binding(
            key=data_key, tenant_id=case.tenant_id, case_id=case.case_id,
            actor=item["actor_principal_id"], evidence_id=item["evidence_id"],
        )
        if expected_scope != item.get("scope_binding") or not verified:
            view = dict(item)
            view["prior_ingestion_status"] = item["ingestion_status"]
            view["ingestion_status"] = "failed" if item.get("scope_binding") != expected_scope else "unavailable"
            view["failure_code"] = "integrity_mismatch" if item.get("scope_binding") != expected_scope else "ciphertext_unavailable"
            view["legal"] = legal_qualities()
            return self._project(view, verified=False)
        return self._project(item, verified=True)

    def _project(self, item: Mapping[str, Any], *, verified: bool) -> dict[str, Any]:
        versions = []
        for version in item.get("artifact_versions") or []:
            versions.append({
                "version": version["version"],
                "kind": version["kind"],
                "integrity_sha256": version["integrity_sha256"],
                "byte_length": version["byte_length"],
                "ciphertext_readback": version.get("ciphertext_readback") is True,
            })
        legal = legal_qualities()
        return {
            "task_id": TASK_ID,
            "evidence_id": item["evidence_id"],
            "tenant_id": item["tenant_id"],
            "case_id": item["case_id"],
            "resource_id": item["resource_id"],
            "actor_principal_id": item["actor_principal_id"],
            "canonical_owner_principal_id": item["canonical_owner_principal_id"],
            "actor_is_canonical_owner": item["actor_is_canonical_owner"],
            "source_filename": item["source_filename"],
            "original_filename": item["original_filename"],
            "media_type": item["media_type"],
            "ingestion_status": item["ingestion_status"],
            "prior_ingestion_status": item.get("prior_ingestion_status") or "",
            "artifact_versions": versions,
            "current_version": item["current_version"],
            "integrity_sha256": item["integrity_sha256"],
            "integrity_verified": verified,
            "scope_binding": item["scope_binding"],
            "complaint_link_id": item.get("complaint_link_id") or "",
            "failure_code": item.get("failure_code") or "",
            "legal": legal,
            "authenticity": legal["authenticity"],
            "relevance": legal["relevance"],
            "admissibility": legal["admissibility"],
            "claim_support": legal["claim_support"],
            "receipt": {
                "ciphertext_readback": bool((item.get("receipt") or {}).get("ciphertext_readback")),
                "establishes_authenticity": False,
                "establishes_relevance": False,
                "establishes_admissibility": False,
                "establishes_claim_support": False,
            },
            "receipt_establishes_legal_quality": False,
            "operation_succeeded": item["ingestion_status"] not in {"failed", "unavailable"},
        }

    def _receipt(self, version: Mapping[str, Any]) -> dict[str, Any]:
        return {"ciphertext_readback": version.get("ciphertext_readback") is True}

    def _identity(self, actor: str, body: Mapping[str, Any], *, content: bool = True, idempotency: bool = True) -> dict[str, str]:
        if not isinstance(body, Mapping):
            raise EvidenceWorkspaceError("request_body")
        rejected = {"cid", "url", "uri", "role", "trusted_local", "key", "passphrase"}
        if any(name in body for name in rejected):
            raise EvidenceWorkspaceError("selector_rejected")
        identity = {
            "actor_principal_id": _label(actor, "actor"),
            "tenant_id": _label(body.get("tenant_id"), "tenant_id"),
            "case_id": _label(body.get("case_id"), "case_id"),
            "resource_id": _label(body.get("resource_id"), "resource_id"),
        }
        if idempotency:
            identity["idempotency_key"] = _label(body.get("idempotency_key"), "idempotency_key")
        if content and "content_base64" not in body:
            raise EvidenceWorkspaceError("content_rejected")
        return identity

    def _reject_legal_claims(self, body: Mapping[str, Any]) -> None:
        for name in LEGAL_QUALITIES:
            if body.get(name) not in {None, "not_established", False}:
                raise EvidenceWorkspaceError("legal_quality_rejected")

    def _content(self, encoded: Any, code: str) -> bytes:
        import base64
        if not isinstance(encoded, str) or encoded.strip() == "":
            raise EvidenceWorkspaceError(code)
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise EvidenceWorkspaceError(code) from exc
        if not payload or len(payload) > _MAX_BYTES:
            raise EvidenceWorkspaceError(code)
        return payload

    def _open(self, identity: Mapping[str, str], *, verify_request: Callable[[], None] | None = None) -> _KeyScope:
        if verify_request is not None:
            verify_request()
        try:
            case = self._directory.select_case(actor_principal_id=identity["actor_principal_id"], case_id=identity["case_id"])
        except CaseDirectoryError as exc:
            raise EvidenceWorkspaceError("not_owner") from exc
        if case.tenant_id != identity["tenant_id"] or case.resource_id != identity["resource_id"]:
            raise EvidenceWorkspaceError("tenant_mismatch")
        session = self._sessions.get(identity["actor_principal_id"])
        if not isinstance(session, UserOwnedKeySession) or not session.unlocked:
            raise EvidenceWorkspaceError("key_unavailable")
        epoch = session.session_epoch
        try:
            key_id = session.ensure_data_key(case.tenant_id, case.case_id)
            data_key = session.lookup_data_key(case.tenant_id, case.case_id, key_id)
        except Exception as exc:
            raise EvidenceWorkspaceError("key_unavailable") from exc
        if not isinstance(data_key, bytes) or len(data_key) != 32:
            raise EvidenceWorkspaceError("key_unavailable")
        scope = _KeyScope(dict(identity), case, session, epoch, key_id, data_key, verify_request)
        self._verify_scope(scope)
        return scope

    def key_scope_verifier(self, actor: str, body: Mapping[str, Any]) -> Callable[[], None]:
        """Capture a live scope for the HTTP boundary's final response check.

        The closure carries no new authority: every call reopens the actual
        case directory and resolves the current active key from its owner.
        No lock remains held while a backend or an HTTP worker runs.
        """
        identity = self._identity(actor, body, content=False, idempotency=False)
        scope = self._open(identity)
        return lambda: self._verify_scope(scope)

    def _verify_scope(self, scope: _KeyScope) -> None:
        # A queued HTTP invocation keeps its original boundary lifetime even
        # if the worker starts after a later unlock. This is an additional
        # constraint; the actual directory and key owner are always rechecked.
        if scope.verify_request is not None:
            scope.verify_request()
        identity, session = scope.identity, scope.session
        if (self._sessions.get(identity["actor_principal_id"]) is not session
                or session.session_epoch != scope.epoch or not session.unlocked):
            raise EvidenceWorkspaceError("key_unavailable")
        try:
            case = self._directory.select_case(
                actor_principal_id=identity["actor_principal_id"], case_id=identity["case_id"])
        except CaseDirectoryError as exc:
            raise EvidenceWorkspaceError("not_owner") from exc
        if (case != scope.case or case.tenant_id != identity["tenant_id"]
                or case.resource_id != identity["resource_id"]):
            raise EvidenceWorkspaceError("tenant_mismatch")
        try:
            key_id, data_key = session.provider().resolve(PrivateArtifactBinding(
                tenant_id=case.tenant_id, case_id=case.case_id,
                artifact_kind=_KIND_CATALOG, revision="scope-check",
                principal_id=case.tenant_id))
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("key_unavailable") from exc
        if (session.session_epoch != scope.epoch or not session.unlocked
                or key_id != scope.key_id or not isinstance(data_key, bytes)
                or not hmac.compare_digest(data_key, scope.data_key)):
            raise EvidenceWorkspaceError("key_unavailable")
        if scope.verify_request is not None:
            scope.verify_request()

    def _pointer(self, identity: Mapping[str, str]) -> Path:
        digest = hashlib.sha256(
            "\n".join((identity["tenant_id"], identity["case_id"], identity["actor_principal_id"])).encode()
        ).hexdigest()
        slot = self._root / digest
        slot.mkdir(mode=0o700, exist_ok=True)
        return slot / "pointer.json"

    def _load(self, identity, case, key_id, data_key, scope) -> dict[str, Any]:
        path = self._pointer(identity)
        if not path.exists():
            self._verify_scope(scope)
            return {"revision": 0, "items": {}, "idempotency": {}}
        pointer = json.loads(path.read_text(encoding="utf-8"))
        cid = pointer.get("cid")
        if not isinstance(cid, str) or cid == "":
            raise EvidenceWorkspaceError("ciphertext_unavailable")
        try:
            opened = retrieve_private_artifact(
                cid,
                access=_Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                artifact_kind=_KIND_CATALOG,
                revision=f"catalog-{pointer.get('revision')}",
                principal_id=case.tenant_id,
                key=data_key,
                key_id=key_id,
                backend=self._backend,
                backend_name=self._backend_name,
            )
        except PrivateStorageError as exc:
            raise EvidenceWorkspaceError("ciphertext_unavailable") from exc
        self._verify_scope(scope)
        data = opened.get("data")
        if not isinstance(data, (bytes, bytearray)):
            raise EvidenceWorkspaceError("ciphertext_unavailable")
        document = json.loads(bytes(data).decode("utf-8"))
        document.setdefault("items", {})
        document.setdefault("idempotency", {})
        return document

    def _save(self, identity, case, key_id, data_key, document: dict[str, Any], scope) -> None:
        self._verify_scope(scope)
        document["revision"] = int(document.get("revision") or 0) + 1
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        stored = store_private_artifact(
            payload,
            access=_Access(trust="authenticated", principal_id=case.tenant_id, case_id=case.case_id),
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind=_KIND_CATALOG,
            revision=f"catalog-{document['revision']}",
            principal_id=case.tenant_id,
            key=data_key,
            key_id=key_id,
            backend=self._backend,
            backend_name=self._backend_name,
            pin_content=False,
        )
        self._verify_scope(scope)
        path = self._pointer(identity)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"cid": stored["cid"], "revision": document["revision"]}), encoding="utf-8")
        os.chmod(temporary, 0o600)
        self._verify_scope(scope)
        os.replace(temporary, path)
