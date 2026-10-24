"""Host-owned execution context for legal and evidence hook operations.

The context is a value and a validation seam. It records the operation,
owner, case, session, graph revision, legal-context identity, consent,
purpose, and deadline. It does not search for law, publish evidence, or
call a provider. Legacy intake and hook callers stay on their existing
paths unless they opt into this context.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence


HOOK_CONTEXT_SCHEMA = "hook_execution_context_receipt_v1"

LEGAL_EVIDENCE_OPERATIONS = (
    "acquire_legal_sources",
    "ingest_private_evidence",
    "refresh_grounding",
)

_REMOTE_BLOCKS_THAT_STILL_ALLOW_CONTEXT = frozenset({
    "privacy_denied:cloud_processing_disabled",
    "privacy_denied:grok_scope_mismatch",
})

_SECRET_FIELD_NAMES = frozenset({
    "key",
    "keys",
    "api_key",
    "passphrase",
    "secret",
    "private_key",
    "token",
    "password",
})


class HookContextError(ValueError):
    """Structural refusal raised before a context exists."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HookExecutionContext:
    """Private host record. Public callers use :meth:`public_receipt`."""

    operation_id: str
    operation: str
    owner_id: str
    case_id: str
    session_id: str
    session_revision: int
    graph_revision: str
    legal_context_id: str
    consent_status: str
    purpose: str
    deadline: datetime
    source_binding_hash: str
    context_binding_hash: str
    source_count: int
    provider_call_allowed: bool

    def public_receipt(self) -> dict[str, Any]:
        return {
            "schema": HOOK_CONTEXT_SCHEMA,
            "operation_id": self.operation_id,
            "operation": self.operation,
            "owner_id": self.owner_id,
            "case_id": self.case_id,
            "session_id": self.session_id,
            "session_revision": self.session_revision,
            "graph_revision": self.graph_revision,
            "legal_context_id": self.legal_context_id,
            "consent_status": self.consent_status,
            "purpose_hash": _sha256_text(self.purpose),
            "deadline": self.deadline.isoformat(),
            "source_binding_hash": self.source_binding_hash,
            "context_binding_hash": self.context_binding_hash,
            "source_count": self.source_count,
        }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(payload: Any, *, prefix: str) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_token(value: Any, *, code: str, max_length: int = 128) -> str:
    if type(value) is not str:
        raise HookContextError(code)
    token = value.strip()
    if not token or len(token) > max_length:
        raise HookContextError(code)
    if any(ord(char) < 32 for char in token):
        raise HookContextError(code)
    return token


def _context_revision(value: Any) -> int:
    if type(value) is bool or value in (None, ""):
        return 0
    if type(value) is not int:
        raise HookContextError("legal_context_missing")
    if value < 0:
        raise HookContextError("legal_context_missing")
    return value


def _date_token(value: Any) -> str:
    if isinstance(value, Mapping):
        return "|".join((
            str(value.get("role") or ""),
            str(value.get("raw_text") or ""),
            str(value.get("start_date") or ""),
            str(value.get("end_date") or ""),
            str(bool(value.get("is_uncertain"))),
        ))
    return str(value or "")


def legal_context_identity(legal_context: Mapping[str, Any] | None) -> str:
    """Opaque identity of the explicit legal context, without question text."""

    if not isinstance(legal_context, Mapping):
        raise HookContextError("legal_context_missing")
    payload = {
        "status": str(legal_context.get("status") or ""),
        "jurisdiction": str(legal_context.get("jurisdiction") or ""),
        "jurisdiction_explicit": bool(legal_context.get("jurisdiction_explicit")),
        "context_revision": _context_revision(legal_context.get("context_revision")),
        "applicable_law_date": _date_token(legal_context.get("applicable_law_date")),
        "event_date": _date_token(legal_context.get("event_date")),
        "filing_reference_date": _date_token(legal_context.get("filing_reference_date")),
        "corpus_retrieval_date": _date_token(legal_context.get("corpus_retrieval_date")),
    }
    return _canonical_hash(payload, prefix="lc_")


def graph_revision_token(graph: Any) -> str:
    """Revision token from ledger indexes and event ids, not statement text."""

    ledger = graph.factual_ledger() if hasattr(graph, "factual_ledger") else {}
    revisions = ledger.get("revisions") if isinstance(ledger, Mapping) else ()
    material = []
    for record in revisions or ():
        if not isinstance(record, Mapping):
            continue
        material.append({
            "revision_index": int(record.get("revision_index") or 0),
            "event_id": str(record.get("event_id") or ""),
        })
    return _canonical_hash({"count": len(material), "revisions": material}, prefix="gr_")


def _reject_secret_fields(record: Mapping[str, Any]) -> None:
    for key in record:
        if str(key).strip().lower() in _SECRET_FIELD_NAMES:
            raise HookContextError("secret_material")


def normalize_source_bindings(source_bindings: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, str], ...]:
    """Keep source id and content hash. Drop raw passages and refuse keys."""

    if source_bindings is None:
        raise HookContextError("source_binding_missing")
    if isinstance(source_bindings, (str, bytes)) or not isinstance(source_bindings, Sequence):
        raise HookContextError("source_binding_missing")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in source_bindings:
        if not isinstance(item, Mapping):
            raise HookContextError("source_binding_missing")
        _reject_secret_fields(item)
        source_id = _require_token(item.get("source_id"), code="source_binding_missing")
        content_hash = item.get("content_hash")
        if type(content_hash) is not str or len(content_hash) != 64:
            raise HookContextError("source_binding_missing")
        try:
            int(content_hash, 16)
        except ValueError as exc:
            raise HookContextError("source_binding_missing") from exc
        # A supplied passage is not retained. It cannot replace the hash.
        if "source_text" in item or "prompt" in item or "source_bytes" in item:
            passage = item.get("source_text")
            if type(passage) is str and passage and _sha256_text(passage) != content_hash:
                raise HookContextError("source_binding_mismatch")
        row = {"source_id": source_id, "content_hash": content_hash}
        identity = (row["source_id"], row["content_hash"])
        if identity in seen:
            raise HookContextError("source_binding_missing")
        seen.add(identity)
        rows.append(row)
    rows.sort(key=lambda row: (row["source_id"], row["content_hash"]))
    return tuple(rows)


def source_binding_hash(source_bindings: Sequence[Mapping[str, Any]] | None) -> str:
    rows = normalize_source_bindings(source_bindings)
    return _canonical_hash([dict(row) for row in rows], prefix="sb_")


def context_binding_hash(*, legal_context_id: str, owner_id: str, case_id: str, session_id: str) -> str:
    return _canonical_hash(
        {
            "legal_context_id": legal_context_id,
            "owner_id": owner_id,
            "case_id": case_id,
            "session_id": session_id,
        },
        prefix="cb_",
    )


def _parse_deadline(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif type(value) is str and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise HookContextError("invalid_deadline") from exc
    else:
        raise HookContextError("invalid_deadline")
    if parsed.tzinfo is None:
        raise HookContextError("invalid_deadline")
    return parsed.astimezone(timezone.utc)


def _consent_status(policy: Mapping[str, Any]) -> str:
    consent = policy.get("consent")
    if not isinstance(consent, Mapping):
        return ""
    return str(consent.get("status") or "")


def intake_consent_rejection(
    privacy_context: Mapping[str, Any] | None,
    *,
    owner_id: str,
    case_id: str,
) -> tuple[Optional[str], str, bool]:
    """Reuse the intake privacy-policy and remote-consent checks.

    A local consent that blocks cloud processing still authorizes this
    context seam, and records that a provider call is not allowed. A
    missing or malformed consent is rejected. The returned status is the
    consent code, never a prompt or key.
    """

    from integrations.ipfs_datasets.llm import _privacy_context_block_reason, inspect_privacy_policy

    if not isinstance(privacy_context, Mapping):
        return "consent_missing", "", False
    if str(privacy_context.get("user_id") or "") != owner_id or str(privacy_context.get("case_id") or "") != case_id:
        return "wrong_case", "", False
    inspection = inspect_privacy_policy(privacy_context.get("policy"), user_id=owner_id, case_id=case_id)
    if not inspection.get("admitted"):
        reason = str(inspection.get("reason") or "consent_missing")
        if reason == "legacy_missing":
            reason = "consent_missing"
        return reason, "", False
    policy = inspection.get("policy") if isinstance(inspection.get("policy"), Mapping) else {}
    status = _consent_status(policy)
    if not status:
        return "consent_missing", "", False
    block = _privacy_context_block_reason(privacy_context, provider="grok_cli", model_name="grok-4.7")
    if block in _REMOTE_BLOCKS_THAT_STILL_ALLOW_CONTEXT:
        return None, status, False
    if block:
        return str(block), status, False
    return None, status, True


def intake_session_revision_rejection(host: Any, expected: int) -> Optional[str]:
    """Same session-revision comparison the intake router uses before dispatch."""

    workflow = getattr(host, "workflow_actions", None)
    meta = getattr(workflow, "_interview_meta", None) if workflow is not None else None
    if not isinstance(meta, dict) or "session_revision" not in meta:
        return None
    if int(meta.get("session_revision") or 0) != int(expected):
        return "stale_request"
    return None


def intake_action_rejection(
    host: Any,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
) -> Optional[str]:
    """When an intake action is already bound, the hook must name that case."""

    action = getattr(host, "_intake_action", None)
    if action is None:
        return None
    try:
        bound_owner, bound_case, bound_session, bound_revision = action[1], action[2], action[3], int(action[4])
    except (TypeError, ValueError, IndexError):
        return "wrong_case"
    if bound_owner != owner_id or bound_case != case_id or bound_session != session_id:
        return "wrong_case"
    if bound_revision != int(session_revision):
        return "stale_request"
    return None


def bind_hook_execution_context(
    *,
    operation: str,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any],
    purpose: str,
    deadline: Any,
    source_bindings: Sequence[Mapping[str, Any]],
    privacy_context: Mapping[str, Any] | None,
    host: Any = None,
) -> HookExecutionContext:
    """Mint a host operation id and freeze the current case bindings."""

    if type(operation) is not str or operation not in LEGAL_EVIDENCE_OPERATIONS:
        raise HookContextError("unsupported_operation")
    owner = _require_token(owner_id, code="wrong_case")
    case = _require_token(case_id, code="wrong_case")
    session = _require_token(session_id, code="wrong_case")
    if type(session_revision) is not int or session_revision < 0:
        raise HookContextError("stale_request")
    revision = _require_token(graph_revision, code="stale_revision", max_length=80)
    if type(purpose) is not str or not purpose.strip():
        raise HookContextError("missing_purpose")
    purpose_text = purpose.strip()
    if len(purpose_text) > 200:
        raise HookContextError("missing_purpose")
    legal_id = legal_context_identity(legal_context)
    rows = normalize_source_bindings(source_bindings)
    consent_code, consent_status, provider_allowed = intake_consent_rejection(
        privacy_context, owner_id=owner, case_id=case,
    )
    if consent_code:
        raise HookContextError(consent_code)
    if host is not None:
        revision_code = intake_session_revision_rejection(host, session_revision)
        if revision_code:
            raise HookContextError(revision_code)
        action_code = intake_action_rejection(
            host, owner_id=owner, case_id=case, session_id=session, session_revision=session_revision,
        )
        if action_code:
            raise HookContextError(action_code)
    return HookExecutionContext(
        operation_id=uuid.uuid4().hex,
        operation=operation,
        owner_id=owner,
        case_id=case,
        session_id=session,
        session_revision=session_revision,
        graph_revision=revision,
        legal_context_id=legal_id,
        consent_status=consent_status,
        purpose=purpose_text,
        deadline=_parse_deadline(deadline),
        source_binding_hash=source_binding_hash(rows),
        context_binding_hash=context_binding_hash(
            legal_context_id=legal_id, owner_id=owner, case_id=case, session_id=session,
        ),
        source_count=len(rows),
        provider_call_allowed=provider_allowed,
    )


def _decision(
    *,
    authorized: bool,
    code: str,
    context: HookExecutionContext | None,
    effect_invoked: bool = False,
) -> dict[str, Any]:
    receipt = context.public_receipt() if context is not None and authorized else (
        context.public_receipt() if context is not None and code not in {"binding_missing"} else None
    )
    # Refusals still expose the opaque receipt when the host context exists,
    # so a caller can correlate the denial without receiving private fields.
    if context is not None and receipt is None and code != "binding_missing":
        receipt = context.public_receipt()
    return {
        "authorized": authorized,
        "code": code,
        "effect_invoked": effect_invoked,
        "effect_dispatched": False,
        "provider_invoked": False,
        "provider_call_allowed": bool(context and context.provider_call_allowed and authorized),
        "receipt": receipt,
    }


def authorize_hook_execution(
    context: HookExecutionContext | None,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any] | None,
    purpose: Any,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    privacy_context: Mapping[str, Any] | None,
    now: datetime,
    host: Any = None,
    storage_available: bool = True,
    request_state: str = "active",
    effect: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> dict[str, Any]:
    """Reject a drifted case before invoking an effect.

    A passed effect runs only after every check succeeds. This module does
    not supply a legal-search, publication, or provider effect.
    """

    if not isinstance(context, HookExecutionContext):
        return _decision(authorized=False, code="binding_missing", context=None)
    if type(purpose) is not str or not purpose.strip():
        return _decision(authorized=False, code="missing_purpose", context=context)
    if purpose.strip() != context.purpose:
        return _decision(authorized=False, code="purpose_mismatch", context=context)
    if (
        type(owner_id) is not str or owner_id.strip() != context.owner_id
        or type(case_id) is not str or case_id.strip() != context.case_id
        or type(session_id) is not str or session_id.strip() != context.session_id
    ):
        return _decision(authorized=False, code="wrong_case", context=context)
    if type(session_revision) is not int or session_revision != context.session_revision:
        return _decision(authorized=False, code="stale_request", context=context)
    if host is not None:
        revision_code = intake_session_revision_rejection(host, context.session_revision)
        if revision_code:
            return _decision(authorized=False, code=revision_code, context=context)
        action_code = intake_action_rejection(
            host,
            owner_id=context.owner_id,
            case_id=context.case_id,
            session_id=context.session_id,
            session_revision=context.session_revision,
        )
        if action_code:
            return _decision(authorized=False, code=action_code, context=context)
    if type(graph_revision) is not str or graph_revision.strip() != context.graph_revision:
        return _decision(authorized=False, code="stale_revision", context=context)
    try:
        current_sources = source_binding_hash(source_bindings)
        current_legal_id = legal_context_identity(legal_context)
    except HookContextError as exc:
        return _decision(authorized=False, code=exc.code, context=context)
    if current_sources != context.source_binding_hash:
        return _decision(authorized=False, code="source_binding_changed", context=context)
    current_context_binding = context_binding_hash(
        legal_context_id=current_legal_id,
        owner_id=context.owner_id,
        case_id=context.case_id,
        session_id=context.session_id,
    )
    if current_legal_id != context.legal_context_id or current_context_binding != context.context_binding_hash:
        return _decision(authorized=False, code="context_binding_changed", context=context)
    consent_code, _status, _provider_allowed = intake_consent_rejection(
        privacy_context, owner_id=context.owner_id, case_id=context.case_id,
    )
    if consent_code:
        return _decision(authorized=False, code=consent_code, context=context)
    if str(request_state or "") == "cancelled":
        return _decision(authorized=False, code="cancelled", context=context)
    if storage_available is False:
        return _decision(authorized=False, code="storage_unavailable", context=context)
    if not isinstance(now, datetime) or now.tzinfo is None:
        return _decision(authorized=False, code="invalid_deadline", context=context)
    if now.astimezone(timezone.utc) > context.deadline:
        return _decision(authorized=False, code="deadline_elapsed", context=context)
    receipt = context.public_receipt()
    effect_invoked = False
    if effect is not None:
        effect(receipt)
        effect_invoked = True
    decision = _decision(authorized=True, code="context_authorized", context=context, effect_invoked=effect_invoked)
    decision["effect_dispatched"] = False
    decision["provider_invoked"] = False
    return decision
