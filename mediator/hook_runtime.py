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


# Declared hook purposes. Model purposes are proposals only: they cannot call
# tools or mark a legal requirement satisfied. Local purposes never dispatch.
MODEL_PURPOSE_IDS = frozenset({"extract_facts", "propose_questions", "explain_candidate"})
LOCAL_ONLY_PURPOSE_IDS = frozenset({"local_extraction", "citation_acquisition", "source_graph_check"})
_PURPOSE_INPUT_LIMIT = 8192
_EXPLANATION_LIMIT = 500
_TOOL_KEYS = frozenset({"tools", "tool_calls", "grok_tools", "invoke_tool", "tool"})
_SATISFACTION_KEYS = frozenset({"requirements_satisfied", "requirement_satisfied", "satisfied_requirements"})


def is_local_only_purpose(purpose_id: Any) -> bool:
    return type(purpose_id) is str and purpose_id in LOCAL_ONLY_PURPOSE_IDS


def is_model_purpose(purpose_id: Any) -> bool:
    return type(purpose_id) is str and purpose_id in MODEL_PURPOSE_IDS


def _purpose_ref_pattern():
    import re
    return re.compile(r"^[A-Za-z0-9_.:-]{1,128}\Z")


def _pinned_route() -> dict[str, Any]:
    from integrations.ipfs_datasets.llm import pinned_hook_inference_route

    return pinned_hook_inference_route()


def inference_purpose_catalog() -> tuple[dict[str, Any], ...]:
    """Bounded purpose declarations. The route pin is the same for every model purpose."""

    route = _pinned_route()
    shared = {
        "inference_owner": route["inference_owner"],
        "provider": route["provider"],
        "model": route["model"],
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
        "tools_allowed": False,
        "may_mark_requirements_satisfied": False,
        "max_input_bytes": _PURPOSE_INPUT_LIMIT,
    }
    return (
        {**shared, "purpose_id": "extract_facts", "dispatch": "model", "allowed_inputs": ("source_text", "target_ref"), "allowed_outputs": ("facts",), "max_output_items": 16},
        {**shared, "purpose_id": "propose_questions", "dispatch": "model", "allowed_inputs": ("gap_code", "target_ref"), "allowed_outputs": ("questions",), "max_output_items": 8},
        {**shared, "purpose_id": "explain_candidate", "dispatch": "model", "allowed_inputs": ("candidate_ref", "gap_code"), "allowed_outputs": ("candidate_ref", "explanation"), "max_output_items": 1},
        {"purpose_id": "local_extraction", "dispatch": "local", "model_dispatch": False, "allowed_inputs": ("source_text", "excerpt"), "allowed_outputs": ("source_start", "source_end", "excerpt"), "tools_allowed": False, "may_mark_requirements_satisfied": False, "max_input_bytes": _PURPOSE_INPUT_LIMIT},
        {"purpose_id": "citation_acquisition", "dispatch": "local", "model_dispatch": False, "allowed_inputs": ("citation", "authority_id"), "allowed_outputs": ("authority_id", "citation", "acquired_locally"), "tools_allowed": False, "may_mark_requirements_satisfied": False, "max_input_bytes": _PURPOSE_INPUT_LIMIT},
        {"purpose_id": "source_graph_check", "dispatch": "local", "model_dispatch": False, "allowed_inputs": ("graph_revision", "source_id", "expected_revision"), "allowed_outputs": ("consistent", "graph_revision", "source_id"), "tools_allowed": False, "may_mark_requirements_satisfied": False, "max_input_bytes": _PURPOSE_INPUT_LIMIT},
    )


def _scan_forbidden(value: Any, *, depth: int = 0) -> Optional[str]:
    if depth > 8:
        return "malformed"
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if name in _TOOL_KEYS:
                return "model_cannot_invoke_tools"
            if name in _SATISFACTION_KEYS:
                return "model_cannot_satisfy_requirements"
            found = _scan_forbidden(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        if len(value) > 64:
            return "malformed"
        for item in value:
            found = _scan_forbidden(item, depth=depth + 1)
            if found:
                return found
    return None


def _bounded_text(value: Any, *, limit: int) -> Optional[str]:
    if type(value) is not str:
        return None
    text = value.strip()
    if not text or len(text.encode("utf-8")) > limit:
        return None
    if any(ord(char) < 32 for char in text):
        return None
    return text


def _as_ref(value: Any) -> Optional[str]:
    text = _bounded_text(value, limit=128)
    if text is None or _purpose_ref_pattern().fullmatch(text) is None:
        return None
    return text


def _validate_purpose_inputs(purpose_id: str, inputs: Any) -> tuple[Optional[str], dict[str, Any]]:
    if not isinstance(inputs, Mapping):
        return "malformed", {}
    code = _scan_forbidden(inputs)
    if code:
        return code, {}
    try:
        encoded = json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return "malformed", {}
    if len(encoded) > _PURPOSE_INPUT_LIMIT:
        return "input_bounds", {}
    if purpose_id == "extract_facts":
        if set(inputs) != {"source_text", "target_ref"}:
            return "input_bounds", {}
        source_text = _bounded_text(inputs.get("source_text"), limit=4096)
        target = _as_ref(inputs.get("target_ref"))
        if source_text is None or target is None:
            return "input_bounds", {}
        return None, {"source_text": source_text, "target_ref": target}
    if purpose_id == "propose_questions":
        if set(inputs) != {"gap_code", "target_ref"}:
            return "input_bounds", {}
        gap = _bounded_text(inputs.get("gap_code"), limit=128)
        target = _as_ref(inputs.get("target_ref"))
        if gap is None or target is None:
            return "input_bounds", {}
        return None, {"gap_code": gap, "target_ref": target}
    if purpose_id == "explain_candidate":
        if set(inputs) != {"candidate_ref", "gap_code"}:
            return "input_bounds", {}
        candidate = _as_ref(inputs.get("candidate_ref"))
        gap = _bounded_text(inputs.get("gap_code"), limit=128)
        if candidate is None or gap is None:
            return "input_bounds", {}
        return None, {"candidate_ref": candidate, "gap_code": gap}
    if purpose_id == "local_extraction":
        if set(inputs) != {"source_text", "excerpt"}:
            return "input_bounds", {}
        source_text = _bounded_text(inputs.get("source_text"), limit=4096)
        excerpt = _bounded_text(inputs.get("excerpt"), limit=500)
        if source_text is None or excerpt is None:
            return "input_bounds", {}
        return None, {"source_text": source_text, "excerpt": excerpt}
    if purpose_id == "citation_acquisition":
        if set(inputs) != {"citation", "authority_id"}:
            return "input_bounds", {}
        citation = _bounded_text(inputs.get("citation"), limit=160)
        authority = _as_ref(inputs.get("authority_id"))
        if citation is None or authority is None:
            return "input_bounds", {}
        return None, {"citation": citation, "authority_id": authority}
    if purpose_id == "source_graph_check":
        if set(inputs) != {"graph_revision", "source_id", "expected_revision"}:
            return "input_bounds", {}
        revision = _bounded_text(inputs.get("graph_revision"), limit=80)
        expected = _bounded_text(inputs.get("expected_revision"), limit=80)
        source_id = _as_ref(inputs.get("source_id"))
        if revision is None or expected is None or source_id is None:
            return "input_bounds", {}
        return None, {"graph_revision": revision, "source_id": source_id, "expected_revision": expected}
    return "undeclared_purpose", {}


def _validate_model_output(purpose_id: str, output: Any, inputs: Mapping[str, Any]) -> tuple[Optional[str], dict[str, Any]]:
    if not isinstance(output, Mapping):
        return "malformed", {}
    code = _scan_forbidden(output)
    if code:
        return code, {}
    from integrations.ipfs_datasets.llm import INTAKE_FACT_FIELDS

    if purpose_id == "extract_facts":
        if set(output) != {"facts"} or type(output.get("facts")) is not list:
            return "malformed", {}
        facts = output["facts"]
        if len(facts) > 16:
            return "malformed", {}
        clean = []
        for item in facts:
            if type(item) is not dict or set(item) != {"field", "value", "target_ref"}:
                return "malformed", {}
            field = item.get("field")
            value = _bounded_text(item.get("value"), limit=500)
            target = _as_ref(item.get("target_ref"))
            if type(field) is not str or field not in INTAKE_FACT_FIELDS or value is None or target is None:
                return "malformed", {}
            if target != inputs["target_ref"]:
                return "malformed", {}
            clean.append({"field": field, "value": value, "target_ref": target})
        return None, {"facts": clean}
    if purpose_id == "propose_questions":
        if set(output) != {"questions"} or type(output.get("questions")) is not list:
            return "malformed", {}
        questions = output["questions"]
        if len(questions) > 8:
            return "malformed", {}
        clean = []
        seen: set[str] = set()
        for item in questions:
            if type(item) is not dict or set(item) != {"question_id", "prompt", "target_ref"}:
                return "malformed", {}
            question_id = _as_ref(item.get("question_id"))
            prompt = _bounded_text(item.get("prompt"), limit=500)
            target = _as_ref(item.get("target_ref"))
            if question_id is None or prompt is None or target is None or target != inputs["target_ref"]:
                return "malformed", {}
            if question_id in seen:
                return "malformed", {}
            seen.add(question_id)
            clean.append({"question_id": question_id, "prompt": prompt, "target_ref": target})
        return None, {"questions": clean}
    if purpose_id == "explain_candidate":
        if set(output) != {"candidate_ref", "explanation"}:
            return "malformed", {}
        candidate = _as_ref(output.get("candidate_ref"))
        explanation = _bounded_text(output.get("explanation"), limit=_EXPLANATION_LIMIT)
        if candidate is None or explanation is None or candidate != inputs["candidate_ref"]:
            return "malformed", {}
        return None, {"candidate_ref": candidate, "explanation": explanation}
    return "undeclared_purpose", {}


def _run_local_purpose(purpose_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    if purpose_id == "local_extraction":
        source = inputs["source_text"].encode("utf-8")
        excerpt = inputs["excerpt"]
        start = inputs["source_text"].find(excerpt)
        if start < 0:
            return {"status": "not_found", "output": None}
        start_byte = len(inputs["source_text"][:start].encode("utf-8"))
        end_byte = start_byte + len(excerpt.encode("utf-8"))
        if source[start_byte:end_byte].decode("utf-8") != excerpt:
            return {"status": "not_found", "output": None}
        return {"status": "local_only", "output": {"source_start": start_byte, "source_end": end_byte, "excerpt": excerpt}}
    if purpose_id == "citation_acquisition":
        return {"status": "local_only", "output": {"authority_id": inputs["authority_id"], "citation": inputs["citation"], "acquired_locally": True}}
    consistent = inputs["graph_revision"] == inputs["expected_revision"]
    return {
        "status": "local_only",
        "output": {"consistent": consistent, "graph_revision": inputs["graph_revision"], "source_id": inputs["source_id"]},
    }


def _purpose_result(
    *,
    purpose_id: str,
    status: str,
    code: str,
    model_dispatched: bool,
    output: Any,
    identity: Optional[dict[str, Any]],
    route: Optional[dict[str, Any]],
    synthetic_transport_invoked: bool = False,
) -> dict[str, Any]:
    return {
        "purpose_id": purpose_id,
        "dispatch": "local" if status == "local_only" else ("model" if model_dispatched and status == "available" else "refused"),
        "status": status,
        "code": code,
        "model_dispatched": model_dispatched,
        "model_dispatch_count": 1 if model_dispatched else 0,
        "provider_invoked": False,
        "synthetic_transport_invoked": synthetic_transport_invoked,
        "requirements_satisfied": False,
        "requirements_satisfied_by_model": False,
        "tools_invoked": False,
        "tools_allowed": False,
        "output": output,
        "route": route or {},
        "identity": identity,
    }


def dispatch_declared_hook_purpose(
    context: HookExecutionContext | None,
    purpose_id: str,
    inputs: Mapping[str, Any] | None,
    *,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    legal_context: Mapping[str, Any] | None,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    privacy_context: Mapping[str, Any] | None,
    now: datetime,
    host: Any = None,
    storage_available: bool = True,
    request_state: str = "active",
    model_transport: Optional[Callable[..., Any]] = None,
    requested_provider: Optional[str] = None,
    requested_model: Optional[str] = None,
    allow_local_fallback: bool = False,
    allow_cross_provider_fallback: bool = False,
) -> dict[str, Any]:
    """Run one declared purpose. Local work never calls the model transport.

    Injected transports are synthetic. This function does not verify a live
    Grok model or build identity.
    """

    from integrations.ipfs_datasets.llm import route_identity_diagnostics

    route = _pinned_route()
    if purpose_id not in MODEL_PURPOSE_IDS and purpose_id not in LOCAL_ONLY_PURPOSE_IDS:
        return _purpose_result(purpose_id=str(purpose_id), status="unavailable", code="undeclared_purpose", model_dispatched=False, output=None, identity=None, route=None)
    code, clean_inputs = _validate_purpose_inputs(purpose_id, inputs)
    if code:
        return _purpose_result(purpose_id=purpose_id, status="refused", code=code, model_dispatched=False, output=None, identity=None, route=route if is_model_purpose(purpose_id) else None)
    if not isinstance(context, HookExecutionContext) or context.purpose != purpose_id:
        return _purpose_result(purpose_id=purpose_id, status="refused", code="purpose_mismatch" if isinstance(context, HookExecutionContext) else "binding_missing", model_dispatched=False, output=None, identity=None, route=None)
    decision = authorize_hook_execution(
        context,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        purpose=purpose_id,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        host=host,
        storage_available=storage_available,
        request_state=request_state,
        effect=None,
    )
    if not decision["authorized"]:
        return _purpose_result(purpose_id=purpose_id, status="refused", code=str(decision["code"]), model_dispatched=False, output=None, identity=None, route=None)
    if is_local_only_purpose(purpose_id):
        if model_transport is not None:
            # Present but unused. Calling it would be an unnecessary model dispatch.
            pass
        local = _run_local_purpose(purpose_id, clean_inputs)
        return _purpose_result(
            purpose_id=purpose_id,
            status=str(local["status"]),
            code=str(local["status"]),
            model_dispatched=False,
            output=local["output"],
            identity=None,
            route=None,
        )
    requested = {
        "router": route["router"],
        "provider": requested_provider if requested_provider is not None else route["provider"],
        "model": requested_model if requested_model is not None else route["model"],
        "build": "",
    }
    if (
        requested["provider"] != route["provider"]
        or requested["model"] != route["model"]
        or requested["router"] != route["router"]
        or allow_local_fallback is not False
        or allow_cross_provider_fallback is not False
        or route["allow_local_fallback"] is not False
        or route["allow_cross_provider_fallback"] is not False
    ):
        identity = route_identity_diagnostics(
            requested=requested,
            selected={"router": "", "provider": "", "model": "", "build": ""},
            observed={"router": "", "provider": "", "model": "", "build": ""},
            transport_kind="synthetic",
        )
        return _purpose_result(purpose_id=purpose_id, status="refused", code="unpinned_route", model_dispatched=False, output=None, identity=identity, route=route)
    if decision.get("provider_call_allowed") is not True:
        return _purpose_result(purpose_id=purpose_id, status="refused", code="provider_not_allowed", model_dispatched=False, output=None, identity=None, route=route)
    selected = {"router": route["router"], "provider": route["provider"], "model": route["model"], "build": ""}
    if model_transport is None:
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        return _purpose_result(purpose_id=purpose_id, status="unavailable", code="model_transport_unavailable", model_dispatched=False, output=None, identity=identity, route=route)
    call = {
        "purpose_id": purpose_id,
        "inputs": clean_inputs,
        "router": route["router"],
        "provider": route["provider"],
        "model": route["model"],
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
        "tools_allowed": False,
        "grok_tools": "",
        "may_mark_requirements_satisfied": False,
    }
    try:
        raw = model_transport(call)
    except Exception:
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code="provider_exception", model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return result
    if not isinstance(raw, Mapping):
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code="malformed", model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return result
    observed = {
        "router": raw.get("observed_router", ""),
        "provider": raw.get("observed_provider", ""),
        "model": raw.get("observed_model", ""),
        "build": raw.get("observed_build", ""),
    }
    identity = route_identity_diagnostics(
        requested=requested,
        selected=selected,
        observed=observed,
        transport_kind="synthetic",
        native_observation_bound=False,
        evidence_class=str(raw.get("evidence_class") or ""),
    )
    transport_status = raw.get("status")
    if transport_status != "available":
        code_text = transport_status if type(transport_status) is str and transport_status else "unavailable"
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code=code_text, model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return result
    out_code, clean_output = _validate_model_output(purpose_id, raw.get("output"), clean_inputs)
    if out_code:
        result = _purpose_result(purpose_id=purpose_id, status="refused", code=out_code, model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return result
    result = _purpose_result(purpose_id=purpose_id, status="available", code="proposal_accepted", model_dispatched=True, output=clean_output, identity=identity, route=route, synthetic_transport_invoked=True)
    result["dispatch"] = "model"
    return result


# Operation contracts. Registration records owners and disabled handlers.
# It does not search, ingest, refresh, persist, or call a provider.
HOOK_OPERATION_REGISTRY_SCHEMA = "hook_operation_registry_v1"
HOOK_OPERATION_REQUEST_SCHEMA = "hook_operation_request_v1"
HOOK_OPERATION_RESULT_SCHEMA = "hook_operation_result_v1"

_EXTRACTION_QUESTION_ROLES = ("extract_facts", "propose_questions", "explain_candidate")
_SOURCE_REF_LIMIT = 8
_HANDLER_CALLS = {"count": 0}

_EFFECT_FIELD_CODES = {
    "tools": "model_cannot_invoke_tools",
    "tool": "model_cannot_invoke_tools",
    "tool_calls": "model_cannot_invoke_tools",
    "grok_tools": "model_cannot_invoke_tools",
    "invoke_tool": "model_cannot_invoke_tools",
    "destination": "model_cannot_supply_destination",
    "destinations": "model_cannot_supply_destination",
    "endpoint": "model_cannot_supply_destination",
    "url": "model_cannot_supply_destination",
    "file_path": "model_cannot_supply_path",
    "path": "model_cannot_supply_path",
    "paths": "model_cannot_supply_path",
    "output_path": "model_cannot_supply_path",
    "provider_command": "model_cannot_supply_provider_command",
    "command": "model_cannot_supply_provider_command",
    "shell": "model_cannot_supply_provider_command",
    "argv": "model_cannot_supply_provider_command",
    "requirements_satisfied": "model_cannot_satisfy_requirements",
    "requirement_satisfied": "model_cannot_satisfy_requirements",
    "satisfied_requirements": "model_cannot_satisfy_requirements",
    "satisfied_nodes": "model_cannot_satisfy_requirements",
    "node_edits": "model_cannot_satisfy_requirements",
    "satisfied_node_edits": "model_cannot_satisfy_requirements",
    "chain": "unbounded_chain",
    "next_operation": "unbounded_chain",
    "next_operations": "unbounded_chain",
}

_OPERATION_FIELDS = {
    "acquire_legal_sources": frozenset({"operation", "role", "target_ref", "source_refs", "citation_ref"}),
    "ingest_private_evidence": frozenset({"operation", "role", "target_ref", "source_refs", "evidence_ref"}),
    "refresh_grounding": frozenset({"operation", "role", "target_ref", "source_refs", "graph_revision"}),
}

_OPERATION_OWNERS = {
    "acquire_legal_sources": "mediator.legal_authority_hooks.LegalAuthoritySearchHook",
    "ingest_private_evidence": "mediator.evidence_hooks.EvidenceStorageHook",
    "refresh_grounding": "mediator.mediator.Mediator.refresh_verified_legal_dependencies",
}

_INDEX_OWNERS = {
    "acquire_legal_sources": "mediator.legal_authority_hooks.LegalAuthoritySearchHook",
    "ingest_private_evidence": "mediator.evidence_hooks.EvidenceStorageHook",
    "refresh_grounding": "mediator.legal_authority_hooks.LegalAuthorityStorageHook",
}


def _disabled_handler(operation: str) -> Callable[[Mapping[str, Any]], Any]:
    def handler(_request: Mapping[str, Any]) -> Any:
        _HANDLER_CALLS["count"] += 1
        raise HookContextError("handler_disabled")

    handler.operation = operation  # type: ignore[attr-defined]
    handler.enabled = False  # type: ignore[attr-defined]
    return handler


_DISABLED_HANDLERS = {name: _disabled_handler(name) for name in LEGAL_EVIDENCE_OPERATIONS}


def operation_handler_call_count() -> int:
    return int(_HANDLER_CALLS["count"])


def _prerequisite_rows(operation: str) -> tuple[dict[str, Any], ...]:
    return (
        {
            "id": "persisted_operation_consent",
            "owner": "integrations.ipfs_datasets.llm",
            "implemented": False,
            "verified": False,
        },
        {
            "id": "encrypted_private_artifact_store",
            "owner": "integrations.ipfs_datasets.storage",
            "implemented": False,
            "verified": False,
        },
        {
            "id": "derived_index_boundary",
            "owner": _INDEX_OWNERS[operation],
            "implemented": False,
            "verified": False,
        },
    )


def legal_evidence_operation_registry() -> tuple[dict[str, Any], ...]:
    """Canonical owners and prerequisites. No operation names a successor."""

    rows = []
    for operation in LEGAL_EVIDENCE_OPERATIONS:
        rows.append({
            "operation": operation,
            "owner": _OPERATION_OWNERS[operation],
            "handler_bound": True,
            "handler_enabled": False,
            "effect_enabled": False,
            "writes_enabled": False,
            "prerequisites": [dict(item) for item in _prerequisite_rows(operation)],
            "next_operations": [],
            "adjacent_roles": list(_EXTRACTION_QUESTION_ROLES),
            "request_schema": HOOK_OPERATION_REQUEST_SCHEMA,
            "result_schema": HOOK_OPERATION_RESULT_SCHEMA,
            "request_fields": sorted(_OPERATION_FIELDS[operation]),
        })
    return tuple(rows)


def register_legal_evidence_operations(*, probes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Bind disabled handlers. Probes and owners are not called."""

    if probes is not None and not isinstance(probes, Mapping):
        raise HookContextError("malformed")
    return {
        "schema": HOOK_OPERATION_REGISTRY_SCHEMA,
        "registered": True,
        "dispatch_enabled": False,
        "writes_enabled": False,
        "handler_enabled": False,
        "provider_invoked": False,
        "backend_invoked": False,
        "storage_invoked": False,
        "handler_call_count": operation_handler_call_count(),
        "operations": [dict(row) for row in legal_evidence_operation_registry()],
    }


def _effect_code(value: Any, *, depth: int = 0) -> Optional[str]:
    if depth > 6:
        return "malformed"
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if name in _EFFECT_FIELD_CODES:
                return _EFFECT_FIELD_CODES[name]
            if name in _SECRET_FIELD_NAMES:
                return "secret_material"
            found = _effect_code(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        if len(value) > 32:
            return "malformed"
        for item in value:
            found = _effect_code(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, str) and ("/" in value or "\\" in value or ".." in value):
        return "model_cannot_supply_path"
    return None


def _clean_source_refs(value: Any) -> tuple[Optional[str], tuple[dict[str, str], ...]]:
    if type(value) is not list or len(value) > _SOURCE_REF_LIMIT:
        return "malformed", ()
    rows = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if type(item) is not dict or set(item) != {"source_id", "content_hash"}:
            return "malformed", ()
        source_id = _as_ref(item.get("source_id"))
        content_hash = item.get("content_hash")
        if source_id is None or type(content_hash) is not str or len(content_hash) != 64:
            return "malformed", ()
        try:
            int(content_hash, 16)
        except ValueError:
            return "malformed", ()
        identity = (source_id, content_hash)
        if identity in seen:
            return "malformed", ()
        seen.add(identity)
        rows.append({"source_id": source_id, "content_hash": content_hash})
    return None, tuple(rows)


def _operation_result(
    *,
    operation: str,
    status: str,
    code: str,
    source_refs: Sequence[Mapping[str, str]] = (),
    owner: str = "",
    prerequisites: Sequence[Mapping[str, Any]] = (),
    role: Optional[str] = None,
) -> dict[str, Any]:
    refused = status == "refused"
    return {
        "schema": HOOK_OPERATION_RESULT_SCHEMA,
        "operation": operation,
        "status": status,
        "code": code,
        "role": role,
        "role_dispatched": False,
        "candidate_status": "refused" if refused else "not_candidate",
        "source_status": "refused" if refused else "not_admitted",
        "support_status": "refused" if refused else "unsupported",
        "proof_status": "not_proof",
        "source_refs": [dict(item) for item in source_refs],
        "source_refs_admitted": False,
        "owner": owner,
        "prerequisites": [dict(item) for item in prerequisites],
        "handler_enabled": False,
        "handler_invoked": False,
        "effect_dispatched": False,
        "provider_invoked": False,
        "backend_invoked": False,
        "storage_invoked": False,
        "writes": 0,
        "dispatch_enabled": False,
    }


def _marked_prerequisites(operation: str, *, key_available: bool, private_store_available: bool, derived_index_ready: bool) -> list[dict[str, Any]]:
    rows = []
    for item in _prerequisite_rows(operation):
        row = dict(item)
        row["verified"] = False
        if item["id"] == "encrypted_private_artifact_store" and (not key_available or not private_store_available):
            row["status"] = "key_unavailable" if not key_available else "private_store_unavailable"
        elif item["id"] == "derived_index_boundary" and not derived_index_ready:
            row["status"] = "derived_index_unready"
        else:
            row["status"] = "unavailable"
        rows.append(row)
    return rows


def dispatch_registered_hook_operation(
    request: Mapping[str, Any] | None,
    *,
    context: HookExecutionContext | None,
    host_targets: Sequence[str],
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
    key_available: bool = True,
    private_store_available: bool = True,
    derived_index_ready: bool = True,
    persisted_consent_verified: bool = False,
    probes: Mapping[str, Any] | None = None,
    effect: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    handler: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> dict[str, Any]:
    """Validate one registered operation and refuse its effect.

    Disabled handlers, probes, and caller effects are not invoked. A true
    persisted-consent flag cannot enable dispatch: that store is not implemented.
    """

    del persisted_consent_verified, effect, handler, probes
    if not isinstance(request, Mapping) or isinstance(request, (str, bytes)):
        return _operation_result(operation="", status="refused", code="malformed")
    proposal = request.get("model_proposal") if "model_proposal" in request else None
    if proposal is not None:
        proposal_code = _effect_code(proposal) or "model_cannot_select_target"
        if proposal_code == "malformed":
            proposal_code = "model_cannot_select_target"
        return _operation_result(operation=str(request.get("operation") or ""), status="refused", code=proposal_code)
    effect_code = _effect_code(request)
    if effect_code:
        return _operation_result(operation=str(request.get("operation") or ""), status="refused", code=effect_code)
    operation = request.get("operation")
    if type(operation) is not str or operation not in _OPERATION_FIELDS:
        return _operation_result(operation=str(operation or ""), status="refused", code="unsupported_operation")
    if set(request) - _OPERATION_FIELDS[operation]:
        return _operation_result(operation=operation, status="refused", code="unknown_field", owner=_OPERATION_OWNERS[operation])
    role = request.get("role")
    if role is not None and role not in _EXTRACTION_QUESTION_ROLES:
        return _operation_result(operation=operation, status="refused", code="undeclared_role", owner=_OPERATION_OWNERS[operation])
    ref_code, source_refs = _clean_source_refs(request.get("source_refs"))
    if ref_code:
        return _operation_result(operation=operation, status="refused", code=ref_code, owner=_OPERATION_OWNERS[operation])
    target = _as_ref(request.get("target_ref"))
    owned = tuple(item for item in host_targets if type(item) is str)
    if target is None or target not in owned:
        return _operation_result(operation=operation, status="refused", code="target_not_host_owned", owner=_OPERATION_OWNERS[operation])
    if operation == "acquire_legal_sources" and request.get("citation_ref") is not None and _as_ref(request.get("citation_ref")) is None:
        return _operation_result(operation=operation, status="refused", code="malformed", owner=_OPERATION_OWNERS[operation])
    if operation == "ingest_private_evidence" and request.get("evidence_ref") is not None and _as_ref(request.get("evidence_ref")) is None:
        return _operation_result(operation=operation, status="refused", code="malformed", owner=_OPERATION_OWNERS[operation])
    if operation == "refresh_grounding":
        revision = request.get("graph_revision")
        if _bounded_text(revision, limit=80) is None:
            return _operation_result(operation=operation, status="refused", code="malformed", owner=_OPERATION_OWNERS[operation])
        if revision != graph_revision:
            return _operation_result(operation=operation, status="refused", code="stale_revision", owner=_OPERATION_OWNERS[operation])
    decision = authorize_hook_execution(
        context,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        purpose=purpose,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        host=host,
        storage_available=storage_available,
        request_state=request_state,
        effect=None,
    )
    prerequisites = _marked_prerequisites(
        operation,
        key_available=key_available is True,
        private_store_available=private_store_available is True,
        derived_index_ready=derived_index_ready is True,
    )
    if not decision["authorized"]:
        return _operation_result(
            operation=operation,
            status="refused",
            code=str(decision["code"]),
            source_refs=source_refs,
            owner=_OPERATION_OWNERS[operation],
            prerequisites=prerequisites,
            role=role if type(role) is str else None,
        )
    if key_available is not True:
        code = "key_unavailable"
    elif private_store_available is not True:
        code = "private_store_unavailable"
    elif derived_index_ready is not True:
        code = "derived_index_unready"
    else:
        code = "prerequisite_unavailable"
    return _operation_result(
        operation=operation,
        status="unavailable",
        code=code,
        source_refs=source_refs,
        owner=_OPERATION_OWNERS[operation],
        prerequisites=prerequisites,
        role=role if type(role) is str else None,
    )


def prepare_remote_hook_query(
    *,
    policy_reader: Callable[[], Any],
    provider_loader: Optional[Callable[[], Any]] = None,
    query_submitter: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    owner_id: str,
    case_id: str,
    purpose: str,
    provider_kind: str,
    data_class: str,
    tools: bool = False,
    citation: Any = None,
    complaint_text: Any = None,
    private_fields: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Read persisted owner/case policy before any provider load or query submit.

    Unknown, missing, local, and revoked consent refuse effectful remote
    dispatch. A synthetic loader result is not a live Grok identity.
    """

    from integrations.ipfs_datasets.llm import (
        bind_remote_invocation,
        evaluate_remote_operation_consent,
        minimize_purpose_query,
    )

    base = {
        "purpose": purpose if type(purpose) is str else "",
        "policy_read": False,
        "provider_loader_called": False,
        "query_submitted": False,
        "effectful": False,
        "status": "refused",
        "code": "consent_missing",
        "query": None,
        "invocation_id": None,
        "tools_authorized": False,
        "complaint_included": False,
        "live_model_identity_verified": False,
        "provider_status": "",
    }
    try:
        record = policy_reader()
    except Exception:
        base["status"] = "unavailable"
        base["code"] = "policy_unavailable"
        return base
    base["policy_read"] = True
    decision = evaluate_remote_operation_consent(
        record,
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind=provider_kind,
        data_class=data_class,
        tools=tools,
    )
    query = minimize_purpose_query(
        purpose,
        private_fields=private_fields,
        citation=citation,
        complaint_text=complaint_text,
    )
    complaint = complaint_text if type(complaint_text) is str else ""
    encoded = json.dumps(query, sort_keys=True, ensure_ascii=False)
    base["query"] = query
    base["complaint_included"] = bool(complaint) and complaint in encoded
    base["tools_authorized"] = False
    if base["complaint_included"]:
        base["code"] = "query_not_minimized"
        base["query"] = None
        return base
    if decision["local_query_allowed"] and not decision["effectful_allowed"]:
        if query_submitter is not None:
            query_submitter(query)
            base["query_submitted"] = True
        base["status"] = "local_only"
        base["code"] = "local_only"
        return base
    if not decision["effectful_allowed"]:
        base["code"] = str(decision["code"])
        base["query"] = None
        return base
    if provider_loader is None:
        base["status"] = "unavailable"
        base["code"] = "provider_unavailable"
        return base
    base["provider_loader_called"] = True
    try:
        loaded = provider_loader()
    except Exception:
        base["status"] = "unavailable"
        base["code"] = "provider_unavailable"
        return base
    provider_status = ""
    if isinstance(loaded, Mapping):
        provider_status = str(loaded.get("status") or "")
    elif loaded is None:
        provider_status = "unavailable"
    else:
        provider_status = "available"
    base["provider_status"] = provider_status
    if provider_status != "available":
        base["status"] = "unavailable"
        base["code"] = "provider_unavailable"
        return base
    invocation_id = bind_remote_invocation(
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind=provider_kind,
        data_class=data_class,
        generation=int(decision["generation"]),
    )
    base["invocation_id"] = invocation_id
    if query_submitter is not None:
        try:
            query_submitter(query)
        except Exception:
            base["status"] = "unavailable"
            base["code"] = "query_unavailable"
            return base
        base["query_submitted"] = True
    base["effectful"] = True
    base["status"] = "available"
    base["code"] = "authorized"
    return base


def accept_late_hook_result(
    *,
    policy_reader: Callable[[], Any],
    invocation_id: str,
    owner_id: str,
    case_id: str,
    result_acceptor: Optional[Callable[[], Any]] = None,
) -> dict[str, Any]:
    """Recheck the persisted policy before accepting a late remote result."""

    from integrations.ipfs_datasets.llm import accept_late_remote_result

    try:
        record = policy_reader()
    except Exception:
        return {
            "accepted": False,
            "code": "policy_unavailable",
            "policy_read": False,
            "acceptor_called": False,
            "live_model_identity_verified": False,
        }
    decision = accept_late_remote_result(
        record,
        invocation_id=invocation_id,
        user_id=owner_id,
        case_id=case_id,
    )
    accepted = decision["accepted"] is True
    acceptor_called = False
    if accepted and result_acceptor is not None:
        result_acceptor()
        acceptor_called = True
    return {
        "accepted": accepted,
        "code": str(decision["code"]),
        "policy_read": True,
        "acceptor_called": acceptor_called,
        "live_model_identity_verified": False,
    }
