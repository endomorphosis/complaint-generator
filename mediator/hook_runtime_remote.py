"""Remote hook query and bounded inference dispatch moved from hook_runtime."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from mediator.hook_runtime import (
    HOOK_DISPATCH_TRACE_SCHEMA,
    HOOK_STAGE_RECEIPT_SCHEMA,
    HookContextError,
    HookExecutionContext,
    LEGAL_EVIDENCE_OPERATIONS,
    LOCAL_ONLY_PURPOSE_IDS,
    MODEL_PURPOSE_IDS,
    _GUI_INFERENCE_HOLDS,
    _INFLIGHT_DISPATCHES,
    _bounded_count,
    _bounded_session_revision,
    _dispatch_guard,
    _gui_grant_code,
    _gui_refusal,
    _pinned_route,
    _purpose_result,
    _reconcile_terminal,
    _run_local_purpose,
    _safe_error_type,
    _safe_request_id,
    _safe_revision_token,
    _stage_status,
    _stamp_invocation_association,
    _validate_model_output,
    _validate_purpose_inputs,
    authorize_hook_execution,
    bind_hook_execution_context,
    is_local_only_purpose,
    is_model_purpose,
    minimal_source_references,
    native_gui_inference_transport,
    source_binding_hash,
)

def dispatch_gui_bounded_inference(
    *,
    policy_record: Mapping[str, Any] | None,
    grant: Mapping[str, Any] | None,
    purpose_id: str,
    inputs: Mapping[str, Any] | None,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    legal_context: Mapping[str, Any] | None,
    owner_id: str,
    case_id: str,
    session_id: str,
    session_revision: int,
    graph_revision: str,
    deadline: Any,
    now: datetime,
    privacy_context: Mapping[str, Any] | None,
    model_transport: Optional[Callable[..., Any]] = None,
    complaint_text: Any = None,
    allow_local_fallback: bool = False,
    allow_cross_provider_fallback: bool = False,
    requested_provider: Optional[str] = None,
    requested_model: Optional[str] = None,
    operation: str = "refresh_grounding",
    timeout: float = 30.0,
    cancel_event: Any = None,
    revision_reader: Optional[Callable[[], Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Dispatch one GUI purpose through the existing consented hook boundary.

    The injected transport is synthetic. A payload that claims a live Grok
    identity is not treated as qualification. Fallback stays disabled. The
    call carries allowed purpose inputs and source id/hash references only.
    Model output is held until :func:`admit_gui_bounded_inference`.
    """

    from integrations.ipfs_datasets.llm import bind_remote_invocation, evaluate_remote_operation_consent

    route = _pinned_route()
    purpose = purpose_id if type(purpose_id) is str else ""
    if purpose not in MODEL_PURPOSE_IDS:
        return _gui_refusal(purpose_id=purpose or str(purpose_id), code="undeclared_purpose", route=None)
    native_route = model_transport is native_gui_inference_transport
    if (allow_local_fallback is not False or allow_cross_provider_fallback is not False
            or requested_provider not in (None, route["provider"])
            or requested_model not in (None, route["model"])):
        return _gui_refusal(purpose_id=purpose, code="unpinned_route", route=route)
    try:
        references = minimal_source_references(source_bindings)
        source_revision = source_binding_hash(source_bindings)
    except HookContextError as exc:
        return _gui_refusal(purpose_id=purpose, code=exc.code, route=route)
    complaint = complaint_text if type(complaint_text) is str else ""
    try:
        encoded_inputs = json.dumps(inputs, sort_keys=True, ensure_ascii=False) if inputs is not None else ""
    except (TypeError, ValueError):
        encoded_inputs = ""
    if complaint and complaint in encoded_inputs:
        return _gui_refusal(purpose_id=purpose, code="query_not_minimized", route=route)
    grant_code = _gui_grant_code(grant, case_id=case_id, source_revision=source_revision)
    if grant_code:
        return _gui_refusal(purpose_id=purpose, code=grant_code, route=route)
    consent = evaluate_remote_operation_consent(
        policy_record,
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind="grok_inference",
        data_class="raw_intake",
        tools=False,
    )
    if consent["effectful_allowed"] is not True:
        return _gui_refusal(purpose_id=purpose, code=str(consent["code"]), route=route)
    try:
        context = bind_hook_execution_context(
            operation=operation,
            owner_id=owner_id,
            case_id=case_id,
            session_id=session_id,
            session_revision=session_revision,
            graph_revision=graph_revision,
            legal_context=legal_context if isinstance(legal_context, Mapping) else {},
            purpose=purpose,
            deadline=deadline,
            source_bindings=source_bindings,
            privacy_context=privacy_context,
        )
    except HookContextError as exc:
        return _gui_refusal(purpose_id=purpose, code=exc.code, route=route)
    observed: list[dict[str, Any]] = []

    def observing(call: Mapping[str, Any]) -> Any:
        forwarded = dict(call)
        forwarded["source_references"] = [dict(row) for row in references]
        forwarded["allow_local_fallback"] = False
        forwarded["allow_cross_provider_fallback"] = False
        observed.append(forwarded)
        if model_transport is None:
            return {"status": "unavailable"}
        return model_transport(forwarded)

    invocation_id = bind_remote_invocation(
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose,
        provider_kind="grok_inference",
        data_class="raw_intake",
        generation=int(consent["generation"]),
    )
    if native_route:
        import math
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60
                or not callable(revision_reader)):
            return _gui_refusal(purpose_id=purpose, code="live_revalidation_required", route=route)
        fresh = revision_reader()
        if (not isinstance(fresh, Mapping) or fresh.get("record") != policy_record
                or fresh.get("grant") != grant or fresh.get("graph_revision") != graph_revision
                or fresh.get("session_revision") != session_revision):
            return _gui_refusal(purpose_id=purpose, code="stale_request", route=route)
        current = datetime.now(timezone.utc)
        remaining = min(float(timeout), (context.deadline - current).total_seconds())
        if remaining <= 0 or (cancel_event is not None and cancel_event.is_set()):
            return _gui_refusal(purpose_id=purpose, code="deadline_expired" if remaining <= 0 else "cancelled", route=route)
        result = native_gui_inference_transport({
            "context": context, "purpose_id": purpose, "inputs": inputs,
            "owner_id": owner_id, "case_id": case_id, "session_id": session_id,
            "session_revision": session_revision, "graph_revision": graph_revision,
            "legal_context": legal_context, "source_bindings": source_bindings,
            "privacy_context": privacy_context, "now": current, "consent_record": policy_record,
            "revision_reader": revision_reader, "cancel_event": cancel_event, "timeout": remaining,
            "provider_source_references": references,
        })
    else:
        result = dispatch_declared_hook_purpose(
        context,
        purpose,
        inputs,
        owner_id=owner_id,
        case_id=case_id,
        session_id=session_id,
        session_revision=session_revision,
        graph_revision=graph_revision,
        legal_context=legal_context,
        source_bindings=source_bindings,
        privacy_context=privacy_context,
        now=now,
        model_transport=observing,
        requested_provider=requested_provider,
        requested_model=requested_model,
        allow_local_fallback=False,
        allow_cross_provider_fallback=False,
    )
    result["router_calls"] = observed
    result["source_references"] = [dict(row) for row in references]
    result["invocation_id"] = invocation_id
    result["accepted"] = False
    result["live_model_identity_verified"] = native_route and result.get("live_model_identity_verified") is True
    result["requirements_satisfied"] = False
    result["requirements_satisfied_by_model"] = False
    result["bound_source_revision"] = source_revision
    result["bound_grant_generation"] = int(grant["generation"]) if isinstance(grant, Mapping) else 0
    result["bound_graph_revision"] = graph_revision
    result["bound_session_revision"] = session_revision
    result["consent_generation"] = int(consent["generation"])
    result["limitations"] = (
        "current_call_native_observation_only" if native_route else "synthetic_transport_does_not_qualify_live_model",
        "development_authorization_is_not_case_consent",
        "provider_output_is_not_verified_legal_support",
        "output_waits_for_late_admission",
    )
    if result.get("status") == "available" and result.get("output") is not None:
        _GUI_INFERENCE_HOLDS[invocation_id] = {
            "output": result["output"],
            "owner_id": owner_id,
            "case_id": case_id,
            "purpose": purpose,
            "source_revision": source_revision,
            "grant_id": str(grant.get("grant_id")) if isinstance(grant, Mapping) else "",
            "grant_generation": int(grant["generation"]) if isinstance(grant, Mapping) else 0,
            "graph_revision": graph_revision,
            "session_revision": session_revision,
            "invocation_id": invocation_id,
            "observation": {"transport_kind": "native_observation" if native_route else "synthetic",
                "provider_invoked": result.get("provider_invoked") is True,
                "live_model_identity_verified": result.get("live_model_identity_verified") is True,
                "native_observation_bound": bool((result.get("identity") or {}).get("native_observation_bound")),
                "request_id": str(result.get("request_id") or "")},
        }
        result["output"] = None
        result["status"] = "held"
        result["code"] = "awaiting_late_admission"
    return result

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
    request_id = uuid.uuid4().hex

    def finish_synthetic(result: dict[str, Any], identity: Mapping[str, Any] | None) -> dict[str, Any]:
        marked = dict(identity or {})
        marked["transport_kind"] = "synthetic"
        marked["native_observation_bound"] = False
        marked["synthetic_transport_invoked"] = True
        marked["live_model_identity_verified"] = False
        result["request_id"] = request_id
        result["provider_replayed"] = False
        result["live_model_identity_verified"] = False
        return _stamp_invocation_association(
            result,
            purpose=purpose_id,
            case_id=case_id,
            session_id=session_id,
            graph_revision=graph_revision,
            request_id=request_id,
            receipt=marked,
        )

    guard_key, guard_open = _dispatch_guard("declared", case_id, session_id, purpose_id, graph_revision)
    if not guard_open:
        replay = _purpose_result(purpose_id=purpose_id, status="refused", code="duplicate_dispatch", model_dispatched=False, output=None, identity=None, route=route)
        replay["provider_replayed"] = False
        replay["request_id"] = request_id
        return replay
    try:
        raw = model_transport(call)
    except Exception:
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code="provider_exception", model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    finally:
        _INFLIGHT_DISPATCHES.discard(guard_key)
    if not isinstance(raw, Mapping):
        identity = route_identity_diagnostics(requested=requested, selected=selected, observed={"router": "", "provider": "", "model": "", "build": ""}, transport_kind="synthetic")
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code="malformed", model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
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
    identity["native_observation_bound"] = False
    identity["evidence_class"] = "synthetic"
    transport_status = raw.get("status")
    if transport_status != "available":
        code_text = transport_status if type(transport_status) is str and transport_status else "unavailable"
        result = _purpose_result(purpose_id=purpose_id, status="unavailable", code=code_text, model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    out_code, clean_output = _validate_model_output(purpose_id, raw.get("output"), clean_inputs)
    if out_code:
        result = _purpose_result(purpose_id=purpose_id, status="refused", code=out_code, model_dispatched=True, output=None, identity=identity, route=route, synthetic_transport_invoked=True)
        result["dispatch"] = "refused"
        return finish_synthetic(result, identity)
    result = _purpose_result(purpose_id=purpose_id, status="available", code="proposal_accepted", model_dispatched=True, output=clean_output, identity=identity, route=route, synthetic_transport_invoked=True)
    result["dispatch"] = "model"
    return finish_synthetic(result, identity)

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

def record_bounded_hook_outcome(observation: Mapping[str, Any] | None) -> dict[str, Any]:
    """Record ordered operation, request, revision, and outcome receipts.

    Diagnostics do not call a provider, retry, or copy error text, tool
    payloads, prompts, or source bytes. Stage failure stays visible.
    """

    raw = observation if isinstance(observation, Mapping) and not isinstance(observation, (str, bytes)) else {}
    operation = raw.get("operation") if raw.get("operation") in LEGAL_EVIDENCE_OPERATIONS else ""
    counts = raw.get("counts") if isinstance(raw.get("counts"), Mapping) else {}
    seen = _bounded_count(counts.get("seen", raw.get("seen")))
    admitted = _bounded_count(counts.get("admitted", raw.get("admitted")))
    if admitted > seen:
        admitted = seen
    errors = _bounded_count(counts.get("errors", raw.get("errors")))
    terminal, search, admission, code = _reconcile_terminal(
        str(raw.get("terminal") or ""),
        str(raw.get("source_search") or ""),
        str(raw.get("admission") or ""),
        str(raw.get("code") or ""),
    )
    if terminal != "successful" and errors == 0 and terminal not in {"empty"}:
        errors = 1
    if terminal == "successful":
        errors = 0
    operation_status = _stage_status(raw.get("operation_status"), "recorded" if operation else "malformed")
    request_status = _stage_status(raw.get("request_status"), "recorded" if operation else "malformed")
    revision_status = _stage_status(raw.get("revision_status"), "recorded" if operation else "not_reached")
    if terminal == "malformed" and operation_status == "recorded" and not operation:
        operation_status = "malformed"
        request_status = "malformed"
        revision_status = "not_reached"
    if terminal in {"cancelled", "timeout"} and revision_status == "recorded":
        pass
    outcome_status = terminal
    # No earlier receipt may claim success when the outcome is not success.
    if outcome_status != "successful":
        for label, status in (
            ("operation", operation_status),
            ("request", request_status),
            ("revision", revision_status),
        ):
            if status == "successful":
                if label == "operation":
                    operation_status = "recorded"
                elif label == "request":
                    request_status = "recorded"
                else:
                    revision_status = "recorded"
    request_id = _safe_request_id(raw.get("request_id"))
    session_revision = _bounded_session_revision(raw.get("session_revision"))
    graph_revision = _safe_revision_token(raw.get("graph_revision"))
    error_type = _safe_error_type(raw.get("error_type"))
    receipts = [
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 1,
            "kind": "operation",
            "operation": operation,
            "status": operation_status,
            "code": code if operation_status in {"malformed", "denied", "cancelled", "timeout", "unavailable"} else "recorded",
        },
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 2,
            "kind": "request",
            "request_id": request_id,
            "status": request_status,
            "code": code if request_status in {"malformed", "denied", "cancelled", "timeout", "unavailable"} else "recorded",
        },
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 3,
            "kind": "revision",
            "session_revision": session_revision,
            "graph_revision": graph_revision,
            "status": revision_status,
            "code": code if revision_status in {"malformed", "denied", "cancelled", "timeout", "unavailable"} else "recorded",
        },
        {
            "schema": HOOK_STAGE_RECEIPT_SCHEMA,
            "ordinal": 4,
            "kind": "outcome",
            "status": outcome_status,
            "code": code,
            "source_search": search,
            "admission": admission,
            "error_type": error_type,
            "counts": {"seen": seen, "admitted": admitted, "errors": errors},
            "provider_invoked": False,
            "fallback_used": False,
            "retry_count": 0,
            "effect_dispatched": False,
            "backend_completed": False,
            "requirements_satisfied": False,
            "tool_payload_logged": False,
        },
    ]
    return {
        "schema": HOOK_DISPATCH_TRACE_SCHEMA,
        "ordered": True,
        "request_id": request_id,
        "terminal": terminal,
        "code": code,
        "source_search": search,
        "admission": admission,
        "receipts": receipts,
        "provider_invoked": False,
        "fallback_used": False,
        "retry_count": 0,
        "hides_failure": False,
    }
