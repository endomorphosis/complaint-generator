"""Canonical legal IR compilation moved out of the datasets logic owner.

The moved callables keep the owner module globals so shared receipts, caches,
and the supported-execution marker stay one object.
"""

from __future__ import annotations

import types

def compile_canonical_legal_ir(
    source_text: str,
    *,
    request_id: str,
    vocabulary: Mapping[str, Sequence[str]],
    legal_context: Mapping[str, Any] | None = None,
    user_facts: Sequence[str] | None = None,
    admitted_law: Mapping[str, Any] | None = None,
    factual_premises: Sequence[Any] | None = None,
    unresolved_assumptions: Sequence[Any] | None = None,
    allow_explicit_partial: bool = False,
    expected_schema_version: str | None = None,
    expected_compiler_interface: str | None = None,
    expected_compiler_config_cid: str | None = None,
    expected_policy_cid: str | None = None,
    expected_pipeline_interface: str | None = None,
    expected_pipeline_cid: str | None = None,
    expected_stage_ids: Sequence[str] | None = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Compile legal text through ``compile_canonical_pipeline`` and map sources.

    User facts are recorded as excluded. They are not appended to the legal
    source, and neither applicability nor claim entailment is claimed.
    A version or schema mismatch does not reuse a cached formalization; the
    previous receipt stays inspectable.
    """

    global _CANONICAL_SUPPORTED_EXECUTION
    identities = canonical_compiler_identities()
    if identities is None:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
        receipt = _receipt_shell(
            status="unavailable",
            capability=capability,
            identities=None,
            reason=capability.reason or _canonical_import_reason(),
            cache_outcome="not_cached",
            extra={"user_facts": [str(item) for item in (user_facts or ())]},
        )
        return _finish(_store_receipt(receipt))

    expected = {
        "source_map_schema": expected_schema_version,
        "compiler_interface": expected_compiler_interface,
        "compiler_config_cid": expected_compiler_config_cid,
        "policy_cid": expected_policy_cid,
        "pipeline_interface": expected_pipeline_interface,
        "pipeline_cid": expected_pipeline_cid,
        "stage_ids": None if expected_stage_ids is None else tuple(expected_stage_ids),
    }
    provided = {
        key: value
        for key, value in expected.items()
        if value is not None and key != "stage_ids" or (key == "stage_ids" and expected_stage_ids is not None)
    }
    mismatched = _identity_mismatch(identities, provided)
    if mismatched:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(
                schema_match=False,
                reason="Requested canonical schema or compiler identity does not match the live pipeline.",
            )
        )
        prior = ""
        if _CANONICAL_FORMALIZATION_CACHE:
            prior = next(reversed(_CANONICAL_FORMALIZATION_CACHE.values()))
        receipt = _receipt_shell(
            status="schema_mismatch",
            capability=capability,
            identities=identities,
            reason=capability.reason or "schema mismatch",
            cache_outcome="invalidated",
            prior_receipt_id=prior,
            mismatched_fields=mismatched,
        )
        return _finish(_store_receipt(receipt))

    legal_text, legal_origin, bound_context, binding_error = _bind_admitted_law(
        source_text, legal_context, admitted_law,
    )
    premise_records, premise_error = _bind_factual_premises(factual_premises, legal_text)
    assumption_records, assumption_error = _bind_unresolved_assumptions(unresolved_assumptions)
    input_error = binding_error or premise_error or assumption_error
    excluded_facts = [str(item) for item in (user_facts or ()) if str(item).strip()]
    for premise in premise_records:
        if premise["text"] not in excluded_facts:
            excluded_facts.append(premise["text"])
    authority_version = _version_from_context(bound_context)
    citation = _citation_from_context(bound_context, request_id)
    if input_error:
        receipt = _binding_failure_receipt(
            identities=identities,
            reason=input_error,
            user_facts=excluded_facts,
            legal_origin=legal_origin,
            authority_version=authority_version,
            factual_premises=premise_records,
            unresolved_assumptions=assumption_records,
        )
        return _finish(_store_receipt(receipt))
    if not str(legal_text or "").strip():
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(
                executed=True,
                status="failed",
                reason="Legal source text is required and is separate from user facts.",
            )
        )
        receipt = _receipt_shell(
            status="failed",
            capability=capability,
            identities=identities,
            reason=capability.reason or "missing legal text",
            cache_outcome="not_cached",
            extra={
                "user_facts": excluded_facts,
                "legal_text_origin": legal_origin,
                "authority_version": authority_version,
                "factual_premises": premise_records,
                "unresolved_assumptions": assumption_records,
                "retained_stage_identities": _retained_stage_identities((), None, identities),
                "stage_evidence": {
                    "kind": "canonical_legal_ir_stage_evidence",
                    "status": "failed",
                    "fabricated_ir": False,
                    "source_map_present": False,
                },
                "establishes_governing_law_meaning": False,
                "proves_claim": False,
                "factual_premises_included_in_source": False,
            },
        )
        return _finish(_store_receipt(receipt))

    try:
        atom_vocabulary = _vocabulary_from_mapping(vocabulary)
        request = _canonical_contracts_module.CompilerRequest(
            source_text=legal_text,
            request_id=str(request_id),
            atom_vocabulary=atom_vocabulary,
            allow_explicit_partial=bool(allow_explicit_partial),
        )
    except (TypeError, ValueError) as exc:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(executed=True, status="failed", reason=str(exc))
        )
        receipt = _receipt_shell(
            status="failed",
            capability=capability,
            identities=identities,
            reason=str(exc),
            cache_outcome="not_cached",
            extra={
            "user_facts": excluded_facts,
            "authority_version": authority_version,
            "factual_premises": premise_records,
            "unresolved_assumptions": assumption_records,
            "retained_stage_identities": _retained_stage_identities((), None, identities),
            "stage_evidence": {
                "kind": "canonical_legal_ir_stage_evidence",
                "status": "failed",
                "fabricated_ir": False,
                "source_map_present": False,
            },
            "establishes_governing_law_meaning": False,
            "proves_claim": False,
        },
        )
        return _finish(_store_receipt(receipt))

    cache_key = _compile_cache_key(
        identities,
        source_cid=request.source_cid,
        request_id=str(request_id),
        vocabulary=atom_vocabulary.to_dict(),
        allow_explicit_partial=bool(allow_explicit_partial),
        authority_version=authority_version,
        citation=citation,
        legal_text_origin=legal_origin,
        excluded_user_facts=excluded_facts,
        factual_premises=premise_records,
        unresolved_assumptions=assumption_records,
    )
    if use_cache and cache_key in _CANONICAL_FORMALIZATION_CACHE:
        cached_id = _CANONICAL_FORMALIZATION_CACHE[cache_key]
        cached = _CANONICAL_FORMALIZATION_RECEIPTS.get(cached_id)
        if (cached is not None and cached.get("identities") == identities
                and _canonical_receipt_has_execution_origin(cached)):
            reused = deepcopy(cached)
            reused["reused"] = True
            reused["cache_outcome"] = "reused"
            reused["cache_key"] = cache_key
            return _finish(reused)

    try:
        pipeline = _canonical_pipeline_module.compile_canonical_pipeline(request)
    except (TypeError, ValueError) as exc:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(executed=True, status="failed", reason=str(exc))
        )
        receipt = _receipt_shell(
            status="failed",
            capability=capability,
            identities=identities,
            reason=str(exc),
            cache_outcome="not_cached",
            extra={
                "user_facts": excluded_facts,
                "cache_key": cache_key,
                "factual_premises": premise_records,
                "unresolved_assumptions": assumption_records,
                "retained_stage_identities": _retained_stage_identities((), None, identities),
                "stage_evidence": {
                    "kind": "canonical_legal_ir_stage_evidence",
                    "status": "failed",
                    "fabricated_ir": False,
                    "source_map_present": False,
                },
                "establishes_governing_law_meaning": False,
                "proves_claim": False,
            },
        )
        return _finish(_store_receipt(receipt))

    result = pipeline.result
    stages = tuple(pipeline.stages)
    status_value = str(getattr(result.status, "value", result.status))
    diagnostics = _unsupported_diagnostics(result, stages)
    stage_payload = _stage_records(stages)
    observed_pipeline_cid = str(pipeline.pipeline_cid)
    if observed_pipeline_cid != identities["pipeline_cid"]:
        capability = classify_canonical_compiler_capability(_canonical_evidence(
            schema_match=False, reason="Executed pipeline identity differs from the current compiler contract.",
        ))
        return _finish(_store_receipt(_receipt_shell(
            status="schema_mismatch", capability=capability, identities=identities,
            reason=capability.reason or "pipeline identity mismatch", cache_outcome="invalidated",
            mismatched_fields=("pipeline_cid",),
        )))
    rules = () if result.canonical_ir is None else tuple(result.canonical_ir.rules)
    span_issues = []
    bridge: Dict[str, Any] | None = None
    if status_value == "success":
        span_issues = _prevalidate_character_spans(legal_text, request.source_cid, result.source_map)
        if not span_issues and rules:
            bridge = _bridge_canonical_source_map(
                source_text=legal_text,
                source_cid=request.source_cid,
                citation=citation,
                entries=result.source_map,
                rules=rules,
                stages=stages,
                identities=identities,
            )
        elif not span_issues and not rules:
            span_issues.append(
                {
                    "code": "empty_formula_coverage",
                    "message": "Successful compile emitted no formulas to trace.",
                    "field_path": "canonical_ir.rules",
                }
            )
    coverage_ok = bool(bridge and bridge.get("coverage_ok"))
    partial = status_value == "success" and bool(result.unsupported_semantics)
    if status_value == "success" and not partial and coverage_ok and not span_issues:
        outcome = "success"
    elif status_value == "success" and partial and coverage_ok and not span_issues:
        outcome = "partial"
    elif status_value == "abstained":
        outcome = "abstained"
    else:
        outcome = "failed"
    reason = ""
    if outcome != "success":
        if span_issues:
            reason = "; ".join(item["message"] for item in span_issues)
        elif bridge is not None and not bridge.get("coverage_ok"):
            reason = "Emitted formulas are not fully traceable to source passages and transformations."
        elif outcome == "partial":
            reason = "Canonical compile retained unsupported semantics as an explicit partial result."
        elif outcome == "abstained":
            reason = "Canonical compile abstained and did not emit a reusable formalization."
        else:
            reason = "Canonical compile failed."
    capability = classify_canonical_compiler_capability(
        _canonical_evidence(
            executed=True,
            status=outcome,
            traceable=coverage_ok,
            source_map_valid=coverage_ok,
            reason=reason,
        )
    )
    if capability.implemented:
        _CANONICAL_SUPPORTED_EXECUTION = {
            "identities": deepcopy(identities),
            "receipt_status": outcome,
        }
    receipt_extra: Dict[str, Any] = {
        "request_id": str(request_id),
        "request_cid": request.request_cid,
        "source_cid": request.source_cid,
        "source_text": legal_text,
        "source_character_length": len(legal_text),
        "source_byte_length": len(legal_text.encode("utf-8")),
        "span_unit": "character",
        "legal_text_origin": legal_origin,
        "authority_version": authority_version,
        "citation": citation,
        "user_facts": excluded_facts,
        "compiler_status": status_value,
        "result_cid": str(result.result_cid),
        "compiler_request": _jsonable(request.to_dict()),
        "compiler_result": _jsonable(result.to_dict()),
        "pipeline_cid": observed_pipeline_cid,
        "stages": stage_payload,
        "unsupported_diagnostics": diagnostics,
        "span_issues": span_issues,
        "cache_key": cache_key,
        "formula_ids": [] if bridge is None else list(bridge["formula_ids"]),
        "passages": [] if bridge is None else list(bridge["passages"]),
        "source_map": None if bridge is None else bridge["source_map"],
        "built_source_map": None if bridge is None else bridge["built_source_map"],
        "source_map_validation": None if bridge is None else bridge["validation"],
        "built_source_map_validation": None if bridge is None else bridge["built_validation"],
        "traceability": None if bridge is None else bridge["traceability"],
        "traces": [] if bridge is None else list(bridge["traces"]),
        "vocabulary": atom_vocabulary.to_dict(),
        "allow_explicit_partial": bool(allow_explicit_partial),
        "factual_premises": premise_records,
        "unresolved_assumptions": assumption_records,
        "factual_premises_included_in_source": False,
        "establishes_governing_law_meaning": False,
        "proves_claim": False,
        "retained_stage_identities": _retained_stage_identities(
            stage_payload,
            None if bridge is None else bridge["source_map"],
            identities,
        ),
        "stage_evidence": {
            "kind": "canonical_legal_ir_stage_evidence",
            "status": outcome,
            "fabricated_ir": False,
            "source_map_present": bridge is not None,
        },
    }
    if any(fact and fact in legal_text for fact in excluded_facts):
        receipt_extra["user_facts_overlap_warning"] = (
            "A user fact string also occurs inside the legal source; it was not added as a fact premise."
        )
    receipt = _receipt_shell(
        status=outcome,
        capability=capability,
        identities=identities,
        reason=reason,
        cache_outcome="stored",
        extra=receipt_extra,
    )
    # Include the compiler result CID so distinct compiles do not share a shell id.
    receipt["receipt_id"] = "canonical-receipt-" + hashlib.sha256(
        f"{result.result_cid}:{cache_key}:{outcome}".encode("utf-8")
    ).hexdigest()[:32]
    return _finish(_store_receipt(receipt, cache_key=cache_key if outcome == "success" else ""))


def attach_canonical_legal_ir_source_obligations(
    source_text: str,
    *,
    request_id: str,
    vocabulary: Mapping[str, Sequence[str]],
    applicability_context: Mapping[str, Any] | None = None,
    legal_context: Mapping[str, Any] | None = None,
    admitted_law: Mapping[str, Any] | None = None,
    factual_premises: Sequence[Any] | None = None,
    user_facts: Sequence[str] | None = None,
    unresolved_assumptions: Sequence[Any] | None = None,
    typed_obligations: Sequence[Any] | None = None,
    current_source: str | None = None,
    emitted_lean: str | None = None,
    supplied_receipt: Mapping[str, Any] | None = None,
    allow_explicit_partial: bool = False,
) -> Dict[str, Any]:
    """Compile current legal source and attach only span-checked typed obligations.

    ``compile_canonical_legal_ir`` and ``verify_canonical_formalization_receipt``
    are the only formalization path. A parsed IR, an internally consistent map,
    or emitted Lean text is recorded as non-authority. A caller-supplied receipt
    mapping is ignored and is not verified as if this process stored it.
    """

    context, context_error = _normalize_applicability_context(applicability_context)
    limitations = [
        "IR parsing is not executed proof.",
        "Internal consistency is not governing legal authority.",
        "Emitted Lean text is not executed proof.",
        "A caller-supplied receipt JSON is not a current-source verification.",
    ]
    rejected: List[Dict[str, Any]] = []
    if supplied_receipt is not None:
        rejected.append({
            "reason": "supplied_receipt_ignored",
            "governing_legal_authority": False,
            "executed_proof": False,
        })
    lean_text = emitted_lean if isinstance(emitted_lean, str) else ""
    if emitted_lean is not None and not isinstance(emitted_lean, str):
        rejected.append({"reason": "emitted_lean_not_text", "lean_text_is_proof": False})
    base: Dict[str, Any] = {
        "schema": CANONICAL_IR_ATTACHMENT_SCHEMA,
        "operation": "attach_canonical_legal_ir_source_obligations",
        "request_id": str(request_id or ""),
        "applicability_context": context,
        "typed_obligations": [],
        "rejected_obligations": rejected,
        "source_spans": [],
        "receipt_id": "",
        "receipt_verification": None,
        "compile_status": "",
        "status": "failed",
        "reason": "",
        "executed_proof": False,
        "governing_legal_authority": False,
        "ir_parse_is_proof": False,
        "consistency_is_proof": False,
        "lean_text_is_proof": False,
        "emitted_lean_character_length": len(lean_text),
        "emitted_lean_sha256": hashlib.sha256(lean_text.encode("utf-8")).hexdigest() if lean_text else "",
        "supplied_receipt_ignored": supplied_receipt is not None,
        "user_facts_are_not_law": True,
        "limitations": limitations,
    }
    if context_error:
        base["status"] = "failed"
        base["reason"] = context_error
        return base
    if not isinstance(source_text, str) or not source_text.strip():
        base["reason"] = "legal_source_required"
        return base
    if not isinstance(vocabulary, Mapping):
        base["reason"] = "vocabulary_required"
        return base
    merged_context = dict(legal_context or {})
    for key in ("jurisdiction", "authority_version", "effective_date", "forum"):
        if key in context and key not in merged_context:
            merged_context[key] = context[key]
    compiled = compile_canonical_legal_ir(
        source_text,
        request_id=str(request_id or ""),
        vocabulary=vocabulary,
        legal_context=merged_context or None,
        admitted_law=admitted_law,
        factual_premises=factual_premises,
        user_facts=user_facts,
        unresolved_assumptions=unresolved_assumptions,
        allow_explicit_partial=allow_explicit_partial,
    )
    base["compile_status"] = str(compiled.get("status") or "")
    base["receipt_id"] = str(compiled.get("receipt_id") or "")
    base["reason"] = str(compiled.get("reason") or "")
    base["establishes_governing_law_meaning"] = False
    base["proves_claim"] = False
    if compiled.get("status") in {"unavailable", "schema_mismatch"} or not base["receipt_id"]:
        base["status"] = str(compiled.get("status") or "unavailable")
        base["reason"] = base["reason"] or "canonical_compiler_unavailable"
        return base
    observed_source = compiled.get("source_text") if isinstance(compiled.get("source_text"), str) else source_text
    checked_source = observed_source if current_source is None else current_source
    if not isinstance(checked_source, str):
        base["status"] = "failed"
        base["reason"] = "current_source_invalid"
        return base
    verification = verify_canonical_formalization_receipt(base["receipt_id"], source_text=checked_source)
    base["receipt_verification"] = {
        "status": verification.get("status"),
        "tampered": verification.get("tampered") is True,
        "traceable": verification.get("traceable") is True,
        "execution_origin_verified": verification.get("execution_origin_verified") is True,
        "reason": verification.get("reason") or "",
        "issue_codes": [
            str(item.get("code"))
            for item in (verification.get("issues") or [])
            if isinstance(item, Mapping) and item.get("code")
        ],
    }
    verified = (
        verification.get("status") == "verified"
        and verification.get("tampered") is not True
        and verification.get("execution_origin_verified") is True
        and checked_source == observed_source
    )
    spans: List[Dict[str, Any]] = []
    if verified:
        for index, passage in enumerate(compiled.get("passages") or []):
            if not isinstance(passage, Mapping):
                rejected.append({"reason": "passage_invalid", "index": index})
                continue
            span = _exact_character_span(checked_source, passage.get("start"), passage.get("end"), passage.get("passage"))
            if span is None:
                rejected.append({"reason": "source_span_mismatch", "index": index, "executed_proof": False})
                continue
            span["source_cid"] = str(passage.get("source_cid") or compiled.get("source_cid") or "")
            span["formula_id"] = str(passage.get("rule_cid") or passage.get("field_path") or f"passage-{index}")
            spans.append(span)
            base["typed_obligations"].append(_typed_obligation_record(
                obligation_id=f"source-span-{index}",
                kind="source_span",
                span=span,
                applicability=context,
                origin="current_source_receipt",
            ))
    else:
        rejected.append({
            "reason": "current_source_receipt_unverified",
            "verification_status": verification.get("status"),
            "executed_proof": False,
            "governing_legal_authority": False,
        })
    for index, item in enumerate(typed_obligations or ()):
        if not isinstance(item, Mapping):
            rejected.append({"reason": "typed_obligation_invalid", "index": index})
            continue
        if item.get("executed_proof") is True or item.get("governing_legal_authority") is True or item.get("discharged") is True:
            rejected.append({
                "reason": "typed_obligation_authority_claim_rejected",
                "index": index,
                "executed_proof": False,
                "governing_legal_authority": False,
            })
            continue
        kind = item.get("kind")
        if kind not in TYPED_SOURCE_OBLIGATION_KINDS or kind == "source_span":
            rejected.append({"reason": "typed_obligation_kind", "index": index})
            continue
        span_in = item.get("source_span") if isinstance(item.get("source_span"), Mapping) else {}
        span = _exact_character_span(
            checked_source if verified else "",
            span_in.get("start"),
            span_in.get("end"),
            span_in.get("text"),
        ) if verified else None
        statement = item.get("statement")
        if span is None or not isinstance(statement, str) or statement != span["text"]:
            rejected.append({
                "reason": "typed_obligation_span_mismatch" if verified else "current_source_receipt_unverified",
                "index": index,
                "executed_proof": False,
            })
            continue
        obligation_id = item.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id.strip() or len(obligation_id) > 80:
            obligation_id = f"typed-{index}"
        base["typed_obligations"].append(_typed_obligation_record(
            obligation_id=obligation_id,
            kind=str(kind),
            span=span,
            applicability=context,
            origin="caller_typed",
        ))
    base["source_spans"] = spans
    base["source_character_length"] = len(checked_source)
    base["source_text_sha256"] = hashlib.sha256(checked_source.encode("utf-8")).hexdigest()
    base["span_unit"] = "character"
    if verified and spans and base["typed_obligations"]:
        base["status"] = "attached"
        base["reason"] = ""
    elif verified:
        base["status"] = "failed"
        base["reason"] = base["reason"] or "no_exact_source_spans"
    else:
        base["status"] = "source_unverified"
        base["reason"] = base["reason"] or "current_source_receipt_unverified"
        base["typed_obligations"] = []
        base["source_spans"] = []
    return base


def generate_bound_legal_ir_proof_obligations(
    sample_or_document: Any = None,
    *,
    canonical_receipt: Mapping[str, Any] | None = None,
    max_obligations: int | None = None,
    claim_id: str = "",
    element_id: str = "",
    asserted_facts: Sequence[Any] | None = None,
    disputed_facts: Sequence[Any] | None = None,
    selected_legal_rules: Sequence[Any] | None = None,
    assumptions: Sequence[Any] | None = None,
    missing_facts: Sequence[Any] | None = None,
    legal_context_version: str = "",
    coverage_status: str = "",
    structural_validation: Mapping[str, Any] | None = None,
    source_text: str | None = None,
    use_cache: bool = True,
    requirement_id: str = "",
    definition_binding: Mapping[str, Any] | None = None,
    adverse_treatment: Any = None,
) -> Dict[str, Any]:
    """Generate native Legal IR obligations and bind them to premise identity.

    Native ``obligation_id`` and ``schema_version`` values are copied unchanged.
    The first-party execution identity also covers source, rule, fact, claim,
    assumption, and checker versions, which native ids omit. Structural checks
    stay structural: they do not entail a claim element.
    """

    if _is_canonical_formalization_receipt(sample_or_document) and canonical_receipt is None:
        canonical_receipt = sample_or_document
        sample_or_document = None
    bridge_name = ""
    if sample_or_document is None and canonical_receipt is not None:
        sample_or_document = modal_ir_from_canonical_formalization(canonical_receipt)
        bridge_name = "proof01_canonical_formalization_receipt"
    source = source_text if source_text is not None else _normalized_text_of(sample_or_document)
    inventory = build_legal_ir_premise_inventory(
        asserted_facts=asserted_facts,
        disputed_facts=disputed_facts,
        selected_legal_rules=selected_legal_rules,
        assumptions=assumptions,
        missing_facts=missing_facts,
        source_text=source,
        coverage_status=coverage_status,
    )
    span_checks = _prevalidate_modal_source_spans(sample_or_document) if sample_or_document is not None else []
    duplicates = _duplicate_local_labels(span_checks)
    document_hash = hashlib.sha256(source.encode("utf-8")).hexdigest() if source else ""
    passage_hashes = [item["verified_source_sha256"] for item in span_checks if item.get("verified_source_sha256")]
    versions = {
        "document_sha256": document_hash,
        "source_passage_sha256": passage_hashes,
        "formula_identity": _formula_identity_digest(sample_or_document) if sample_or_document is not None else "",
        "modal_document_identity": _stable_payload_digest({
            "sample_id": _attr_or_key(sample_or_document, "sample_id", None),
            "document": _mapping_or_empty(_document_view(sample_or_document)),
        }),
        "source_map_identity": _source_map_identity(canonical_receipt),
        "premise_inventory_identity": _stable_payload_digest(inventory),
        "structural_validation_identity": _stable_payload_digest(dict(structural_validation or {})),
        "legal_context_version": str(legal_context_version or (canonical_receipt or {}).get("authority_version") or ""),
        "rule_versions": [
            {
                "premise_id": item.get("premise_id"),
                "version": item.get("version"),
                "revision": item.get("revision"),
            }
            for item in inventory["selected_legal_rules"]
        ],
        "claim_id": str(claim_id or ""),
        "element_id": str(element_id or ""),
        "fact_revisions": [
            {"premise_id": item.get("premise_id"), "revision": item.get("revision"), "text_sha256": item.get("text_sha256")}
            for item in [*inventory["asserted_facts"], *inventory["disputed_facts"], *inventory["missing_facts"]]
        ],
        "assumption_ids": [item.get("premise_id") for item in inventory["assumptions"]],
        "assumption_labels": [item.get("label") for item in inventory["assumptions"]],
        "requirement_id": str(requirement_id or (definition_binding or {}).get("requirement_id") or ""),
        "definition_identity": _definition_binding_identity(definition_binding),
        "assumption_identity": _assumption_binding_identity(inventory, definition_binding),
        "adverse_treatment_identity": _adverse_treatment_identity(adverse_treatment if adverse_treatment is not None else (definition_binding or {}).get("adverse_treatment")),
        "source_identity": document_hash,
        "checker_version": PROOF_OBLIGATION_CHECKER_VERSION,
        "policy_version": PROOF_OBLIGATION_POLICY_VERSION,
        "native_backend": PROOF_OBLIGATION_BACKEND_IDENTITY,
        "coverage_status": str(coverage_status or ""),
        "max_obligations": max_obligations,
    }
    versions["execution_identity"] = _execution_identity(versions)
    cache_key = str(versions["execution_identity"])

    def _unavailable(status: str, support: str, reason: str, *, code: str) -> Dict[str, Any]:
        receipt = _obligation_shell(
            status=status,
            reason=reason,
            support=support,
            backend_available=False,
            inventory=inventory,
            versions=versions,
            extra={
                "bridge": bridge_name,
                "source_span_checks": span_checks,
                "duplicate_local_labels": duplicates,
                "structural_validation": deepcopy(dict(structural_validation or {})),
                "structural_validation_is_entailment": False,
                "operational_trace": [{"code": code, "status": status}],
                "cache_outcome": "not_cached",
            },
        )
        # An unavailable result must not resolve to an earlier successful
        # receipt for this request identity. Keep that history unchanged.
        return receipt

    if _is_pipeline_result(sample_or_document):
        return _unavailable(
            "unsupported",
            "unsupported",
            "CompilerPipelineResult is not a ModalIR document. Use the PROOF01 formalization bridge.",
            code="pipeline_result_not_modal_ir",
        )
    if _legal_ir_obligations_module is None or not hasattr(_legal_ir_obligations_module, "generate_legal_ir_proof_obligations"):
        return _unavailable(
            "unavailable",
            "unsupported",
            "Legal IR proof obligation generator is unavailable.",
            code="generator_unavailable",
        )
    if use_cache and cache_key in _BOUND_OBLIGATION_CACHE:
        cached = _BOUND_OBLIGATION_RECEIPTS.get(_BOUND_OBLIGATION_CACHE[cache_key])
        if cached is not None:
            reused = deepcopy(cached)
            reused["reused"] = True
            reused["cache_outcome"] = "reused"
            return reused
    prior = ""
    if _BOUND_OBLIGATION_CACHE:
        prior = next(reversed(_BOUND_OBLIGATION_CACHE.values()))
    try:
        native = _legal_ir_obligations_module.generate_legal_ir_proof_obligations(
            sample_or_document,
            max_obligations=max_obligations,
        )
    except Exception as exc:  # noqa: BLE001 - typed generator failure without premise text
        return _unavailable(
            "unavailable",
            "unsupported",
            "Legal IR proof obligation generator failed.",
            code=_obligation_error_code(exc),
        )
    native_payloads = []
    native_ids: List[str] = []
    native_schemas: List[str] = []
    for obligation in native or []:
        payload = obligation.to_dict() if hasattr(obligation, "to_dict") else dict(obligation)
        native_payloads.append(payload)
        native_ids.append(str(payload.get("obligation_id") or ""))
        schema = str(payload.get("schema_version") or "")
        if schema and schema not in native_schemas:
            native_schemas.append(schema)
    kinds = {str(item.get("kind") or "") for item in native_payloads}
    unbounded_count = None
    truncated = False
    if max_obligations is not None:
        try:
            limit = max(0, int(max_obligations))
        except (TypeError, ValueError):
            limit = 0
        truncated = len(native_payloads) >= limit
        if truncated:
            try:
                full = _legal_ir_obligations_module.generate_legal_ir_proof_obligations(sample_or_document)
                unbounded_count = len(list(full))
                truncated = unbounded_count > len(native_payloads)
            except Exception:  # noqa: BLE001 - truncation stays marked without echoing the error
                unbounded_count = None
                truncated = True
    spans_verified = bool(span_checks) and all(item.get("verified") for item in span_checks)
    if not _formulas_of(sample_or_document):
        status = "presence_diagnostic"
    elif truncated:
        status = "truncated"
    elif span_checks and not spans_verified:
        status = "source_unverified"
    else:
        status = "success"
    for check in span_checks:
        matched = next(
            (
                item.get("metadata", {}).get("source_span_sha256")
                for item in native_payloads
                if item.get("formula_id") == check["formula_id"] and isinstance(item.get("metadata"), Mapping)
                and item.get("metadata", {}).get("source_span_sha256")
            ),
            "",
        )
        check["native_source_span_sha256"] = str(matched or "")
        if check["verified"] and matched:
            check["native_hash_matches_verified_source"] = matched == check["verified_source_sha256"]
        elif not check["verified"]:
            check["native_hash_matches_verified_source"] = False
            check["native_span_hash_is_fallback"] = True
    trace = [
        {
            "code": "native_obligations_generated",
            "status": status,
            "obligation_count": len(native_payloads),
            "truncated": truncated,
        }
    ]
    if duplicates:
        trace.append({"code": "duplicate_local_labels", "status": "recorded", "count": len(duplicates)})
    if any(not item.get("verified") for item in span_checks):
        trace.append({"code": "source_span_unverified", "status": "native_hash_not_source_bytes"})
    receipt = _obligation_shell(
        status=status,
        reason="",
        support="executed",
        backend_available=True,
        inventory=inventory,
        versions=versions,
        extra={
            "bridge": bridge_name,
            "obligations": native_payloads,
            "native_obligation_ids": native_ids,
            "native_schema_versions": native_schemas,
            "obligation_count": len(native_payloads),
            "unbounded_obligation_count": unbounded_count,
            "truncated": truncated,
            "max_obligations": max_obligations,
            "source_span_checks": span_checks,
            "source_spans_verified": spans_verified,
            "duplicate_local_labels": duplicates,
            "structural_validation": deepcopy(dict(structural_validation or {})),
            "structural_validation_is_entailment": False,
            "obligation_kinds": sorted(kind for kind in kinds if kind and not kind.endswith("Error")),
            "presence_diagnostic": "modal_formula_presence" in kinds,
            "operational_trace": trace,
            "cache_outcome": "stored",
            "prior_receipt_id": prior if prior and prior != ("proof-obligation-" + hashlib.sha256(cache_key.encode()).hexdigest()[:32]) else "",
            "checker_version": PROOF_OBLIGATION_CHECKER_VERSION,
            "policy_version": PROOF_OBLIGATION_POLICY_VERSION,
            "trust_level": PROOF_OBLIGATION_TRUST_STRUCTURAL,
        },
    )
    return _store_obligation_receipt(receipt, cache_key=cache_key)


def ground_bound_formal_analysis(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Run current-bound formal producers and keep non-proof artifacts non-proof.

    Canonical compilation, obligation generation, and ``route_bound_legal_ir_proof``
    are the proof producers. FOL conversion and neurosymbolic parsing are recorded
    as parsed IR. A caller formula, graph packet, classifier score, training
    metric, or fabricated producer packet cannot become executed proof or legal
    sufficiency. A missing producer stays unavailable and unexecuted.
    """

    if not isinstance(payload, Mapping):
        return {
            "status": "refused",
            "code": "malformed_input",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
        }
    source_text = payload.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip():
        return {
            "status": "refused",
            "code": "missing_source_text",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "nonproof": _nonproof_observations(payload),
        }
    source_text = source_text.strip()
    source_version = _binding_token(payload.get("source_version")) or _binding_token(payload.get("current_source_version"))
    definition_identity = _binding_token(payload.get("definition_identity")) or _binding_token(payload.get("current_definition_identity"))
    if not source_version or not definition_identity:
        return {
            "status": "refused",
            "code": "missing_binding",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "nonproof": _nonproof_observations(payload),
        }
    drift = _current_binding_drift(payload, source_text)
    if drift:
        return {
            "status": "unexecuted",
            "code": drift,
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "source_version": source_version,
            "definition_identity": definition_identity,
            "nonproof": _nonproof_observations(payload),
        }

    requirement_id = _binding_token(payload.get("requirement_id")) or "requirement-unspecified"
    citation = _binding_token(payload.get("citation")) or "synthetic-authority"
    premises = [dict(item) for item in payload.get("premises") or [] if isinstance(item, Mapping)]
    for premise in premises:
        premise["text_sha256"] = sha256_utf8(str(premise.get("text") or ""))
    vocabulary = payload.get("vocabulary") if isinstance(payload.get("vocabulary"), Mapping) else {}
    vocabulary = {
        "actors": tuple(vocabulary.get("actors") or ("Employer", "Employee")),
        "actions": tuple(vocabulary.get("actions") or ("retaliate", "oppose")),
        "objects": tuple(vocabulary.get("objects") or ("practice",)),
        "qualifiers": tuple(vocabulary.get("qualifiers") or ()),
    }
    nonproof = _nonproof_observations(payload)
    formula_text = payload.get("parsed_formula")
    if not isinstance(formula_text, str) or not formula_text.strip():
        formula_text = "forall x. Employer(x) -> Obligation(x)"
    neurosymbolic = _neurosymbolic_parse_surface(formula_text.strip())
    fol = text_to_fol(source_text)
    fol_view = {
        "status": fol.get("status"),
        "converter": fol.get("converter"),
        "predicate_count": len(fol.get("predicates") or []),
        "logic_path": (fol.get("metadata") or {}).get("logic_path") if isinstance(fol.get("metadata"), Mapping) else fol.get("logic_path"),
        "executed_proof": False,
        "legal_sufficiency": False,
        "producer": "text_to_fol",
    }
    identities = canonical_compiler_identities()
    if identities is None:
        return {
            "status": "unavailable",
            "code": "missing_producer",
            "execution": "unexecuted",
            "executed_proof": False,
            "legal_sufficiency": False,
            "producer_invoked": False,
            "source_version": source_version,
            "definition_identity": definition_identity,
            "requirement_id": requirement_id,
            "fol": fol_view,
            "neurosymbolic": neurosymbolic,
            "canonical": {"status": "unavailable", "executed_proof": False, "legal_sufficiency": False},
            "obligations": {"status": "unexecuted", "executed_proof": False},
            "route": {"outcome": "unavailable", "executed_proof": False, "producer_invoked": False},
            "nonproof": nonproof,
        }
    compiled = compile_canonical_legal_ir(
        source_text,
        request_id=requirement_id,
        vocabulary=vocabulary,
        legal_context={"citation": citation, "authority_version": source_version},
        factual_premises=premises,
        admitted_law={
            "source_text": source_text,
            "source_sha256": sha256_utf8(source_text),
            "authority_version": source_version,
            "definition_identity": definition_identity,
            "citation": citation,
        },
    )
    canonical_view = {
        "status": compiled.get("status"),
        "reason": compiled.get("reason"),
        "entails_claim": compiled.get("entails_claim") is True,
        "entails_applicability": compiled.get("entails_applicability") is True,
        "executed_proof": False,
        "legal_sufficiency": False,
        "producer": "compile_canonical_legal_ir",
    }
    obligations = generate_bound_legal_ir_proof_obligations(
        None,
        canonical_receipt=compiled if isinstance(compiled, Mapping) else None,
        source_text=source_text,
        asserted_facts=premises,
        requirement_id=requirement_id,
        definition_binding={
            "requirement_id": requirement_id,
            "definition_identity": definition_identity,
            "source_version": source_version,
        },
        legal_context_version=source_version,
        max_obligations=4,
    )
    obligation_view = {
        "status": obligations.get("status"),
        "support": obligations.get("support"),
        "execution_identity": (obligations.get("versions") or {}).get("execution_identity") if isinstance(obligations.get("versions"), Mapping) else "",
        "obligation_count": obligations.get("obligation_count") or 0,
        "structural_validation_is_entailment": obligations.get("structural_validation_is_entailment") is True,
        "executed_proof": False,
        "legal_sufficiency": False,
        "producer": "generate_bound_legal_ir_proof_obligations",
    }
    versions = obligations.get("versions") if isinstance(obligations.get("versions"), Mapping) else {}
    routed = route_bound_legal_ir_proof(
        goal_statement=source_text,
        premise_inventory=obligations.get("premise_inventory") if isinstance(obligations.get("premise_inventory"), Mapping) else None,
        execution_identity=str(versions.get("execution_identity") or ""),
        expected_execution_identity=str(versions.get("execution_identity") or ""),
        requirement_id=requirement_id,
        expected_requirement_id=requirement_id,
        definition_identity=str(versions.get("definition_identity") or definition_identity),
        expected_definition_identity=str(versions.get("definition_identity") or definition_identity),
        assumption_identity=str(versions.get("assumption_identity") or ""),
        expected_assumption_identity=str(versions.get("assumption_identity") or ""),
        adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
        expected_adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
        source_identity=str(versions.get("source_identity") or sha256_utf8(source_text)),
        expected_source_identity=str(versions.get("source_identity") or sha256_utf8(source_text)),
        premise_version=str((obligations.get("premise_inventory") or {}).get("digest") or "") if isinstance(obligations.get("premise_inventory"), Mapping) else "",
        expected_premise_version=str((obligations.get("premise_inventory") or {}).get("digest") or "") if isinstance(obligations.get("premise_inventory"), Mapping) else "",
        total_timeout_seconds=2.0,
        similarity_score=payload.get("classifier_score"),
        model_assertion=payload.get("fake_producer"),
    )
    executed_proof = _proof_from_live_route(routed)
    route_view = {
        "outcome": routed.get("outcome"),
        "reason": routed.get("reason"),
        "substantive_trust_satisfied": routed.get("substantive_trust_satisfied") is True,
        "structural_proof_is_substantive": routed.get("structural_proof_is_substantive") is True,
        "structural_route_proved": routed.get("structural_route_proved") is True,
        "similarity_score_ignored": routed.get("similarity_score_ignored") is True,
        "model_assertion_ignored": routed.get("model_assertion_ignored") is True,
        "routing_receipt_id": routed.get("routing_receipt_id"),
        "attempt_count": len(routed.get("attempts") or []),
        "executed_proof": executed_proof,
        "legal_sufficiency": False,
        "producer": "route_bound_legal_ir_proof",
        "producer_invoked": True,
    }
    return {
        "status": "grounded",
        "code": "producer_result",
        "execution": str(routed.get("outcome") or "unknown"),
        "executed_proof": executed_proof,
        "legal_sufficiency": False,
        "producer_invoked": True,
        "source_version": source_version,
        "definition_identity": definition_identity,
        "requirement_id": requirement_id,
        "source_hash": sha256_utf8(source_text),
        "fol": fol_view,
        "neurosymbolic": neurosymbolic,
        "canonical": canonical_view,
        "obligations": obligation_view,
        "route": route_view,
        "nonproof": nonproof,
    }


from . import logic as _logic_owner
from .logic import (
    CANONICAL_IR_ATTACHMENT_SCHEMA,
    PROOF_OBLIGATION_BACKEND_IDENTITY,
    PROOF_OBLIGATION_CHECKER_VERSION,
    PROOF_OBLIGATION_POLICY_VERSION,
    PROOF_OBLIGATION_TRUST_STRUCTURAL,
    TYPED_SOURCE_OBLIGATION_KINDS,
    _BOUND_OBLIGATION_CACHE,
    _BOUND_OBLIGATION_RECEIPTS,
    _CANONICAL_FORMALIZATION_CACHE,
    _CANONICAL_FORMALIZATION_RECEIPTS,
    _adverse_treatment_identity,
    _assumption_binding_identity,
    _attr_or_key,
    _bind_admitted_law,
    _bind_factual_premises,
    _bind_unresolved_assumptions,
    _binding_failure_receipt,
    _binding_token,
    _bridge_canonical_source_map,
    _canonical_contracts_module,
    _canonical_evidence,
    _canonical_import_reason,
    _canonical_pipeline_module,
    _canonical_receipt_has_execution_origin,
    _citation_from_context,
    _compile_cache_key,
    _current_binding_drift,
    _definition_binding_identity,
    _document_view,
    _duplicate_local_labels,
    _exact_character_span,
    _execution_identity,
    _finish,
    _formula_identity_digest,
    _formulas_of,
    _identity_mismatch,
    _is_canonical_formalization_receipt,
    _is_pipeline_result,
    _jsonable,
    _legal_ir_obligations_module,
    _mapping_or_empty,
    _neurosymbolic_parse_surface,
    _nonproof_observations,
    _normalize_applicability_context,
    _normalized_text_of,
    _obligation_error_code,
    _obligation_shell,
    _prevalidate_character_spans,
    _prevalidate_modal_source_spans,
    _proof_from_live_route,
    _receipt_shell,
    _retained_stage_identities,
    _source_map_identity,
    _stable_payload_digest,
    _stage_records,
    _store_obligation_receipt,
    _store_receipt,
    _typed_obligation_record,
    _unsupported_diagnostics,
    _version_from_context,
    _vocabulary_from_mapping,
    build_legal_ir_premise_inventory,
    canonical_compiler_identities,
    modal_ir_from_canonical_formalization,
    route_bound_legal_ir_proof,
    sha256_utf8,
    text_to_fol,
    verify_canonical_formalization_receipt
)

def _bind_to_owner_globals(function):
    """Execute a moved function against the owner module globals."""

    rebound = types.FunctionType(
        function.__code__,
        _logic_owner.__dict__,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = dict(getattr(function, "__annotations__", {}))
    rebound.__dict__.update(function.__dict__)
    return rebound

compile_canonical_legal_ir = _bind_to_owner_globals(compile_canonical_legal_ir)
_logic_owner.compile_canonical_legal_ir = compile_canonical_legal_ir

attach_canonical_legal_ir_source_obligations = _bind_to_owner_globals(attach_canonical_legal_ir_source_obligations)
_logic_owner.attach_canonical_legal_ir_source_obligations = attach_canonical_legal_ir_source_obligations

generate_bound_legal_ir_proof_obligations = _bind_to_owner_globals(generate_bound_legal_ir_proof_obligations)
_logic_owner.generate_bound_legal_ir_proof_obligations = generate_bound_legal_ir_proof_obligations

ground_bound_formal_analysis = _bind_to_owner_globals(ground_bound_formal_analysis)
_logic_owner.ground_bound_formal_analysis = ground_bound_formal_analysis

