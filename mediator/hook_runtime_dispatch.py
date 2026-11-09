"""Hook effect dispatch functions moved from hook_runtime."""

from __future__ import annotations

from typing import (
    Mapping,
)

from mediator.hook_runtime import (
    EFFECT_ACCEPTANCE_SCHEMA,
    EFFECT_RECEIPT_SCHEMA,
    HookContextError,
    HookExecutionContext,
    LOCAL_ONLY_PURPOSE_IDS,
    MODEL_PURPOSE_IDS,
    _INFLIGHT_DISPATCHES,
    _bounded_association_token,
    _candidate_acquisition,
    _canonical_hash,
    _dispatch_guard,
    _graph_effect_fingerprint,
    _hook_observation_receipt,
    _inquiry_token,
    _normalize_effect_records,
    _payload_mismatch_code,
    _pending_revision_token,
    _pinned_route,
    _purpose_result,
    _refusal,
    _remember_candidate,
    _require_token,
    _run_local_purpose,
    _stamp_invocation_association,
    _validate_model_output,
    _validate_purpose_inputs,
    authorize_hook_execution,
    context_binding_hash,
    graph_revision_token,
    is_local_only_purpose,
    is_model_purpose,
    legal_context_identity,
    minimal_source_references,
    normalize_source_bindings,
    saved_case_hash,
    source_binding_hash,
)


def dispatch_observed_hook_purpose(
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
    consent_record: Mapping[str, Any] | None = None,
    pending_case: Any = None,
    revision_reader: Optional[Callable[[], Mapping[str, Any]]] = None,
    cancel_event: Any = None,
    timeout: float = 30.0,
    data_class: str = "raw_intake",
    provider_kind: str = "grok_inference",
    provider_source_references: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dispatch a declared hook purpose through the Native observation seam.

    Injected synthetic transports stay on ``dispatch_declared_hook_purpose``.
    This path does not substitute another model, does not enable tools, and
    does not write the pending case. Timeout, cancellation, quota, and
    malformed output return a bounded receipt and leave that revision in place.
    """

    import json as _json
    import uuid as _uuid

    from integrations.ipfs_datasets.llm import (
        accept_late_remote_result,
        bind_remote_invocation,
        evaluate_remote_operation_consent,
        generate_observed_hook_purpose,
        route_identity_diagnostics,
    )

    route = _pinned_route()
    pending_revision = _pending_revision_token(pending_case, graph_revision)
    pending_before = _json.dumps(pending_case, sort_keys=True, default=str) if pending_case is not None else None

    def seal(result: dict[str, Any]) -> dict[str, Any]:
        if pending_before is not None:
            after = _json.dumps(pending_case, sort_keys=True, default=str)
            result["pending_revision_recoverable"] = after == pending_before
            result["case_revision_mutated"] = after != pending_before
        else:
            result["pending_revision_recoverable"] = True
            result["case_revision_mutated"] = False
        result["pending_revision"] = pending_revision
        result["requirements_satisfied"] = False
        result["requirements_satisfied_by_model"] = False
        result["tools_invoked"] = False
        result["tools_allowed"] = False
        result["live_canary"] = False
        if result.get("identity") is None or result["identity"].get("live_model_identity_verified") is not True:
            result["live_model_identity_verified"] = False
        else:
            result["live_model_identity_verified"] = True
        observed_receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
        _stamp_invocation_association(
            result,
            purpose=purpose_id,
            case_id=case_id,
            session_id=session_id,
            graph_revision=graph_revision,
            request_id=str(result.get("request_id") or observed_receipt.get("request_id") or ""),
            receipt={
                **observed_receipt,
                "transport_kind": (result.get("identity") or {}).get("transport_kind") if isinstance(result.get("identity"), Mapping) else observed_receipt.get("transport_kind"),
                "native_observation_bound": (result.get("identity") or {}).get("native_observation_bound") if isinstance(result.get("identity"), Mapping) else False,
                "evidence_class": (result.get("identity") or {}).get("evidence_class") if isinstance(result.get("identity"), Mapping) else "",
                "live_model_identity_verified": result.get("live_model_identity_verified") is True,
                "synthetic_transport_invoked": result.get("synthetic_transport_invoked") is True,
            },
        )
        return result

    if purpose_id not in MODEL_PURPOSE_IDS and purpose_id not in LOCAL_ONLY_PURPOSE_IDS:
        refused = _purpose_result(purpose_id=str(purpose_id), status="unavailable", code="undeclared_purpose", model_dispatched=False, output=None, identity=None, route=None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=str(purpose_id), status="unavailable", code="undeclared_purpose", request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    code, clean_inputs = _validate_purpose_inputs(purpose_id, inputs)
    if code:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=code, model_dispatched=False, output=None, identity=None, route=route if is_model_purpose(purpose_id) else None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=code, request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    if not isinstance(context, HookExecutionContext) or context.purpose != purpose_id:
        mismatch = "purpose_mismatch" if isinstance(context, HookExecutionContext) else "binding_missing"
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=mismatch, model_dispatched=False, output=None, identity=None, route=None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=mismatch, request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
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
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=str(decision["code"]), model_dispatched=False, output=None, identity=None, route=None)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=str(decision["code"]), request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    if is_local_only_purpose(purpose_id):
        local = _run_local_purpose(purpose_id, clean_inputs)
        result = _purpose_result(purpose_id=purpose_id, status=str(local["status"]), code=str(local["status"]), model_dispatched=False, output=local["output"], identity=None, route=None)
        result["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status=str(local["status"]), code=str(local["status"]), request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(result)
    if decision.get("provider_call_allowed") is not True:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code="provider_not_allowed", model_dispatched=False, output=None, identity=None, route=route)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code="provider_not_allowed", request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    consent = evaluate_remote_operation_consent(
        consent_record,
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose_id,
        provider_kind=provider_kind,
        data_class=data_class,
        tools=False,
    )
    if consent["effectful_allowed"] is not True:
        refused = _purpose_result(purpose_id=purpose_id, status="refused", code=str(consent["code"]), model_dispatched=False, output=None, identity=None, route=route)
        refused["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code=str(consent["code"]), request_id="", pending_revision=pending_revision, identity=None, accepted=False)
        return seal(refused)
    requested = {"router": route["router"], "provider": route["provider"], "model": route["model"], "build": ""}
    selected = dict(requested)
    request_id = _uuid.uuid4().hex
    guard_key, guard_open = _dispatch_guard("observed", case_id, session_id, purpose_id, graph_revision)
    if not guard_open:
        replay = _purpose_result(purpose_id=purpose_id, status="refused", code="duplicate_dispatch", model_dispatched=False, output=None, identity=None, route=route)
        replay["provider_replayed"] = False
        replay["request_id"] = request_id
        replay["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused", code="duplicate_dispatch", request_id=request_id, pending_revision=pending_revision, identity=None, accepted=False)
        return seal(replay)
    invocation_id = bind_remote_invocation(
        user_id=owner_id,
        case_id=case_id,
        purpose=purpose_id,
        provider_kind=provider_kind,
        data_class=data_class,
        generation=int(consent["generation"]),
    )
    generation_inputs = dict(clean_inputs)
    if provider_source_references is not None:
        try:
            references = minimal_source_references(source_bindings)
            if tuple(dict(row) for row in provider_source_references) != references:
                raise HookContextError("source_binding_mismatch")
        except (HookContextError, TypeError, ValueError):
            _INFLIGHT_DISPATCHES.discard(guard_key)
            return seal(_purpose_result(purpose_id=purpose_id, status="refused", code="source_binding_mismatch",
                model_dispatched=False, output=None, identity=None, route=route))
        generation_inputs["source_references"] = [dict(row) for row in references]
    try:
        observed_call = generate_observed_hook_purpose(
            purpose_id=purpose_id,
            inputs=generation_inputs,
            request_id=request_id,
            timeout=timeout,
            cancel_event=cancel_event,
        )
    finally:
        _INFLIGHT_DISPATCHES.discard(guard_key)
    identity = route_identity_diagnostics(
        requested=requested,
        selected=selected,
        observed={
            "router": observed_call.get("observed_router") or "",
            "provider": observed_call.get("observed_provider") or "",
            "model": observed_call.get("observed_model") or "",
            "build": observed_call.get("observed_build") or "",
        },
        transport_kind="native_observation",
        native_observation_bound=observed_call.get("native_observation_bound") is True,
        evidence_class=str(observed_call.get("evidence_class") or ""),
    )
    # The diagnostics helper can mark a qualified Native class as live. A
    # loaded test double must not inherit that claim.
    if observed_call.get("live_model_identity_verified") is not True:
        identity["live_model_identity_verified"] = False
        identity["live_build_identity_verified"] = False
    identity["native_observation_bound"] = observed_call.get("native_observation_bound") is True
    identity["evidence_class"] = _bounded_association_token(observed_call.get("evidence_class"), 80)
    if identity["native_observation_bound"] is not True:
        identity["live_model_identity_verified"] = False
        identity["live_build_identity_verified"] = False
    failure = str(observed_call.get("code") or "unavailable")
    if failure != "available":
        status = "unavailable" if failure not in {"cancelled", "timeout", "quota", "malformed"} else failure
        if failure in {"substitution_refused", "route_unverified"}:
            status = "unavailable"
        result = _purpose_result(
            purpose_id=purpose_id,
            status=status if status != "malformed" else "refused",
            code=failure,
            model_dispatched=bool(observed_call.get("model_dispatched")),
            output=None,
            identity=identity,
            route=route,
        )
        result["dispatch"] = "refused"
        result["provider_invoked"] = bool(observed_call.get("model_dispatched"))
        result["synthetic_transport_invoked"] = False
        result["invocation_id"] = invocation_id
        result["request_id"] = request_id
        result["accepted"] = False
        result["receipt"] = _hook_observation_receipt(
            purpose_id=purpose_id, status=result["status"], code=failure, request_id=request_id,
            pending_revision=pending_revision, identity=identity, accepted=False,
        )
        return seal(result)

    def current_late() -> dict[str, Any]:
        if revision_reader is None:
            return {
                "graph_revision": graph_revision,
                "session_revision": session_revision,
                "record": consent_record,
            }
        state = revision_reader()
        if not isinstance(state, Mapping):
            return {"graph_revision": "", "session_revision": None, "record": None}
        return {
            "graph_revision": state.get("graph_revision"),
            "session_revision": state.get("session_revision"),
            "record": state.get("record", consent_record),
        }

    try:
        late_state = current_late()
    except Exception:
        # Authorization/session/key/source reproof failed after the observed
        # provider call. Refuse output without erasing the dispatch fact.
        result = _purpose_result(purpose_id=purpose_id, status="refused", code="late_revalidation_unavailable",
            model_dispatched=True, output=None, identity=identity, route=route)
        result.update(dispatch="refused", provider_invoked=True, synthetic_transport_invoked=False,
            invocation_id=invocation_id, request_id=request_id, accepted=False)
        result["receipt"] = _hook_observation_receipt(purpose_id=purpose_id, status="refused",
            code="late_revalidation_unavailable", request_id=request_id, pending_revision=pending_revision,
            identity=identity, accepted=False)
        return seal(result)
    late = accept_late_remote_result(
        late_state.get("record"),
        invocation_id=invocation_id,
        user_id=owner_id,
        case_id=case_id,
        bound_graph_revision=graph_revision,
        current_graph_revision=late_state.get("graph_revision") if type(late_state.get("graph_revision")) is str else "",
        bound_session_revision=session_revision,
        current_session_revision=late_state.get("session_revision") if type(late_state.get("session_revision")) is int else -1,
    )
    if late["accepted"] is not True:
        result = _purpose_result(
            purpose_id=purpose_id, status="refused", code=str(late["code"]),
            model_dispatched=True, output=None, identity=identity, route=route,
        )
        result["dispatch"] = "refused"
        result["provider_invoked"] = True
        result["synthetic_transport_invoked"] = False
        result["invocation_id"] = invocation_id
        result["request_id"] = request_id
        result["accepted"] = False
        result["receipt"] = _hook_observation_receipt(
            purpose_id=purpose_id, status="refused", code=str(late["code"]), request_id=request_id,
            pending_revision=pending_revision, identity=identity, accepted=False,
        )
        return seal(result)
    try:
        parsed = _json.loads(observed_call.get("output_text") or "")
    except (TypeError, ValueError):
        parsed = None
    out_code, clean_output = _validate_model_output(purpose_id, parsed, clean_inputs)
    if out_code:
        result = _purpose_result(
            purpose_id=purpose_id, status="refused", code="malformed" if out_code == "malformed" else out_code,
            model_dispatched=True, output=None, identity=identity, route=route,
        )
        result["dispatch"] = "refused"
        result["provider_invoked"] = True
        result["synthetic_transport_invoked"] = False
        result["accepted"] = False
        result["request_id"] = request_id
        result["invocation_id"] = invocation_id
        result["receipt"] = _hook_observation_receipt(
            purpose_id=purpose_id, status="refused", code=result["code"], request_id=request_id,
            pending_revision=pending_revision, identity=identity, accepted=False,
        )
        return seal(result)
    result = _purpose_result(
        purpose_id=purpose_id, status="available", code="proposal_accepted",
        model_dispatched=True, output=clean_output, identity=identity, route=route,
    )
    result["dispatch"] = "model"
    result["provider_invoked"] = True
    result["synthetic_transport_invoked"] = False
    result["accepted"] = True
    result["request_id"] = request_id
    result["invocation_id"] = invocation_id
    result["receipt"] = _hook_observation_receipt(
        purpose_id=purpose_id, status="available", code="proposal_accepted", request_id=request_id,
        pending_revision=pending_revision, identity=identity, accepted=True,
    )
    return seal(result)
def accept_bound_hook_effect(
    *,
    context: HookExecutionContext | None,
    graph: Any,
    source_bindings: Sequence[Mapping[str, Any]] | None,
    legal_context: Mapping[str, Any] | None,
    request_id: Any,
    records: Sequence[Mapping[str, Any]] | None = None,
    pending_inquiry: Any = None,
    saved_case: Mapping[str, Any] | None = None,
    bound_pending_inquiry: Any = None,
    bound_saved_case_hash: str | None = None,
    result_state: str = "active",
    storage_available: bool = True,
    acquisition_log: list | None = None,
) -> dict[str, Any]:
    """Admit one hook effect once, bound to the current preimages and graph revision.

    Candidate acquisition is recorded on ``acquisition_log`` only. It is not an
    admitted source, evidence, or support record. An effect receipt does not
    establish durability or proof. Replay of the same request, preimages, and
    accepted graph revision returns the stored admission. A changed preimage,
    stale revision, cancelled result, or stale result does not mutate the graph,
    the pending inquiry, or the saved case.
    """

    from complaint_phases.knowledge_graph import answer_event_fingerprint, answer_event_payload

    operation = context.operation if isinstance(context, HookExecutionContext) else ""
    request_token = request_id if type(request_id) is str else ""
    source_preimage = ""
    context_preimage = ""
    graph_revision = context.graph_revision if isinstance(context, HookExecutionContext) else ""
    if graph is None or not hasattr(graph, "factual_ledger") or not hasattr(graph, "append_revision"):
        candidate = _candidate_acquisition(
            operation=operation,
            request_id=request_token,
            source_preimage="",
            context_preimage="",
            records=(),
            status="unavailable",
        )
        _remember_candidate(acquisition_log, candidate)
        receipt = _refusal(
            code="graph_unavailable",
            candidate=candidate,
            operation=operation,
            request_id=request_token,
            source_preimage="",
            context_preimage="",
            graph_revision=graph_revision,
            graph_fingerprint=_graph_effect_fingerprint(graph),
            pending_fingerprint=_canonical_hash(pending_inquiry, prefix="inq_"),
            case_fingerprint=_canonical_hash(saved_case, prefix="casebody_"),
            graph=graph,
            pending_inquiry=pending_inquiry,
            saved_case=saved_case,
        )
        receipt["mutated_graph"] = False
        receipt["mutated_pending_inquiry"] = False
        receipt["mutated_saved_case"] = False
        return receipt

    graph_fingerprint = _graph_effect_fingerprint(graph)
    pending_fingerprint = _canonical_hash(pending_inquiry, prefix="inq_")
    case_fingerprint = _canonical_hash(saved_case, prefix="casebody_")

    def refuse(code: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
        _remember_candidate(acquisition_log, candidate)
        return _refusal(
            code=code,
            candidate=candidate,
            operation=operation,
            request_id=request_token,
            source_preimage=source_preimage,
            context_preimage=context_preimage,
            graph_revision=graph_revision,
            graph_fingerprint=graph_fingerprint,
            pending_fingerprint=pending_fingerprint,
            case_fingerprint=case_fingerprint,
            graph=graph,
            pending_inquiry=pending_inquiry,
            saved_case=saved_case,
        )

    if not isinstance(context, HookExecutionContext):
        candidate = _candidate_acquisition(
            operation="", request_id=request_token, source_preimage="", context_preimage="", records=(), status="failed",
        )
        return refuse("binding_missing", candidate)
    try:
        request_token = _require_token(request_id, code="malformed")
        rows = normalize_source_bindings(source_bindings)
        source_preimage = source_binding_hash(rows)
        legal_id = legal_context_identity(legal_context)
        context_preimage = context_binding_hash(
            legal_context_id=legal_id,
            owner_id=context.owner_id,
            case_id=context.case_id,
            session_id=context.session_id,
        )
        effect_records = _normalize_effect_records(records)
        if bound_saved_case_hash is not None and not isinstance(saved_case, Mapping) and saved_case is not None:
            raise HookContextError("malformed")
        current_inquiry = _inquiry_token(pending_inquiry)
        bound_inquiry = None if bound_pending_inquiry is None else _inquiry_token(bound_pending_inquiry)
    except HookContextError as exc:
        candidate = _candidate_acquisition(
            operation=operation,
            request_id=request_id if type(request_id) is str else "",
            source_preimage=source_preimage,
            context_preimage=context_preimage,
            records=(),
            status="failed",
        )
        return refuse(exc.code, candidate)

    candidate_status = "acquired" if effect_records else "empty"
    candidate = _candidate_acquisition(
        operation=operation,
        request_id=request_token,
        source_preimage=source_preimage,
        context_preimage=context_preimage,
        records=effect_records,
        status=candidate_status,
    )
    if source_preimage != context.source_binding_hash:
        return refuse("source_preimage_changed", candidate)
    if context_preimage != context.context_binding_hash or legal_id != context.legal_context_id:
        return refuse("context_preimage_changed", candidate)
    if storage_available is not True:
        failed = dict(candidate)
        failed["candidate_status"] = "unavailable"
        return refuse("storage_unavailable", failed)
    state = result_state if type(result_state) is str else "malformed"
    if state == "cancelled":
        return refuse("cancelled", candidate)
    if state == "stale":
        return refuse("stale_result", candidate)
    if state == "timeout":
        failed = dict(candidate)
        failed["candidate_status"] = "failed"
        return refuse("timeout", failed)
    if state != "active":
        return refuse("malformed", candidate)
    if bound_pending_inquiry is not None and current_inquiry != bound_inquiry:
        return refuse("stale_inquiry", candidate)
    if bound_saved_case_hash is not None:
        try:
            current_case_hash = saved_case_hash(saved_case if isinstance(saved_case, Mapping) else None)
        except HookContextError as exc:
            return refuse(exc.code, candidate)
        if current_case_hash != bound_saved_case_hash:
            return refuse("stale_case", candidate)

    record_ids = {
        "source": [row["record_id"] for row in effect_records if row["kind"] == "source"],
        "evidence": [row["record_id"] for row in effect_records if row["kind"] == "evidence"],
        "support": [row["record_id"] for row in effect_records if row["kind"] == "support"],
    }
    payload = answer_event_payload(
        question=operation,
        answer=request_token,
        source_context={
            "source_preimage": source_preimage,
            "context_preimage": context_preimage,
            "graph_revision": context.graph_revision,
            "records": [dict(row) for row in effect_records],
        },
    )
    event_id = f"hook-effect:{operation}:{request_token}"
    ledger = graph.factual_ledger()
    events = ledger.get("answer_events") or {}
    existing = events.get(event_id) if isinstance(events, Mapping) else None
    if isinstance(existing, Mapping):
        if existing.get("fingerprint") == answer_event_fingerprint(payload):
            stored = existing.get("stored_acceptance")
            if isinstance(stored, Mapping) and isinstance(stored.get("effect_receipt"), Mapping):
                _remember_candidate(acquisition_log, stored.get("candidate_acquisition") or candidate)
                return {
                    "schema": EFFECT_ACCEPTANCE_SCHEMA,
                    "accepted": True,
                    "code": "accepted",
                    "idempotent_replay": True,
                    "candidate_acquisition": dict(stored.get("candidate_acquisition") or candidate),
                    "effect_receipt": dict(stored["effect_receipt"]),
                    "mutated_graph": _graph_effect_fingerprint(graph) != graph_fingerprint,
                    "mutated_pending_inquiry": _canonical_hash(pending_inquiry, prefix="inq_") != pending_fingerprint,
                    "mutated_saved_case": _canonical_hash(saved_case, prefix="casebody_") != case_fingerprint,
                }
        else:
            existing_payload = existing.get("payload") if isinstance(existing.get("payload"), Mapping) else {}
            return refuse(
                _payload_mismatch_code(existing_payload, source_preimage, context_preimage, context.graph_revision),
                candidate,
            )

    current_revision = graph_revision_token(graph)
    if current_revision != context.graph_revision:
        return refuse("stale_revision", candidate)

    receipt = {
        "schema": EFFECT_RECEIPT_SCHEMA,
        "accepted": True,
        "code": "accepted",
        "effect_id": event_id,
        "operation": operation,
        "request_id": request_token,
        "source_preimage": source_preimage,
        "context_preimage": context_preimage,
        "accepted_graph_revision": context.graph_revision,
        "revision_index": None,
        "source_ids": list(record_ids["source"]),
        "evidence_ids": list(record_ids["evidence"]),
        "support_ids": list(record_ids["support"]),
        "durable": False,
        "proof": False,
        "proof_status": "not_proof",
    }
    revision = graph.append_revision({
        "action": "hook_effect",
        "event_id": event_id,
        "source_preimage": source_preimage,
        "context_preimage": context_preimage,
        "accepted_graph_revision": context.graph_revision,
        "source_ids": list(record_ids["source"]),
        "evidence_ids": list(record_ids["evidence"]),
        "support_ids": list(record_ids["support"]),
    })
    receipt["revision_index"] = revision.get("revision_index")
    admitted = graph.factual_ledger().setdefault("hook_effect_records", {})
    admitted[event_id] = [dict(row) for row in effect_records]
    stored_acceptance = {
        "candidate_acquisition": dict(candidate),
        "effect_receipt": dict(receipt),
    }
    graph.finish_answer_event(event_id, payload, stored_acceptance=stored_acceptance)
    _remember_candidate(acquisition_log, candidate)
    return {
        "schema": EFFECT_ACCEPTANCE_SCHEMA,
        "accepted": True,
        "code": "accepted",
        "idempotent_replay": False,
        "candidate_acquisition": dict(candidate),
        "effect_receipt": dict(receipt),
        "mutated_graph": True,
        "mutated_pending_inquiry": _canonical_hash(pending_inquiry, prefix="inq_") != pending_fingerprint,
        "mutated_saved_case": _canonical_hash(saved_case, prefix="casebody_") != case_fingerprint,
    }
