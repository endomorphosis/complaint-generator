"""Temporal reasoning moved out of the datasets logic owner.

The moved callables keep the owner module globals so shared helpers and
temporal bounds stay one object.
"""

from __future__ import annotations

import types


def _build_temporal_formula_for_fact(event_symbol: str, temporal_fact: Dict[str, Any]) -> Dict[str, str]:
    start_date = temporal_fact.get("start_date")
    end_date = temporal_fact.get("end_date") or start_date
    is_range = bool(temporal_fact.get("is_range", False)) or (start_date and end_date and start_date != end_date)
    is_approximate = bool(temporal_fact.get("is_approximate", False))
    start_symbol = _normalize_time_symbol(start_date)
    end_symbol = _normalize_time_symbol(end_date, fallback=start_symbol)

    if start_date and not is_range:
        tdfol_formula = f"forall t (AtTime(t,{start_symbol}) -> Fact({event_symbol},t))"
        dcec_formula = f"Happens({event_symbol},{start_symbol})"
    elif start_date and end_date:
        tdfol_formula = f"forall t (During(t,{start_symbol},{end_symbol}) -> Fact({event_symbol},t))"
        dcec_formula = f"HoldsDuring({event_symbol},{start_symbol},{end_symbol})"
    else:
        tdfol_formula = f"forall t (Fact({event_symbol},t))"
        dcec_formula = f"Observed({event_symbol})"

    if is_approximate:
        tdfol_formula = f"{tdfol_formula} and Approximate({event_symbol})"
        dcec_formula = f"{dcec_formula} and ApproximateTime({event_symbol})"

    return {
        "tdfol": tdfol_formula,
        "dcec": dcec_formula,
    }


def _normalize_claim_support_temporal_handoff(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    def _normalize_text_list(items: Any) -> List[str]:
        normalized_items: List[str] = []
        for item in items if isinstance(items, list) else []:
            text = str(item or "").strip()
            if text and text not in normalized_items:
                normalized_items.append(text)
        return normalized_items

    normalized = {
        "claim_type": str(value.get("claim_type") or "").strip(),
        "claim_element_id": str(value.get("claim_element_id") or "").strip(),
        "unresolved_temporal_issue_count": int(value.get("unresolved_temporal_issue_count", 0) or 0),
        "chronology_task_count": int(value.get("chronology_task_count", 0) or 0),
        "unresolved_temporal_issue_ids": _normalize_text_list(value.get("unresolved_temporal_issue_ids")),
        "event_ids": _normalize_text_list(value.get("event_ids")),
        "temporal_fact_ids": _normalize_text_list(value.get("temporal_fact_ids")),
        "temporal_relation_ids": _normalize_text_list(value.get("temporal_relation_ids")),
        "timeline_issue_ids": _normalize_text_list(value.get("timeline_issue_ids")),
        "temporal_issue_ids": _normalize_text_list(value.get("temporal_issue_ids")),
        "temporal_proof_bundle_ids": _normalize_text_list(value.get("temporal_proof_bundle_ids")),
        "temporal_proof_objectives": _normalize_text_list(value.get("temporal_proof_objectives")),
    }
    if not normalized["claim_type"]:
        normalized.pop("claim_type")
    if not normalized["claim_element_id"]:
        normalized.pop("claim_element_id")
    if not normalized.get("unresolved_temporal_issue_count") and not normalized.get("chronology_task_count") and not any(
        normalized[key]
        for key in (
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ):
        return {}
    return normalized


def _normalize_temporal_proof_bundle(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bundle = deepcopy(value)
    proof_bundle_id = str(bundle.get("proof_bundle_id") or "").strip()
    theorem_exports = bundle.get("theorem_exports")
    if not isinstance(theorem_exports, dict):
        theorem_exports = {}
        bundle["theorem_exports"] = theorem_exports
    tdfol_formulas = [
        str(formula).strip()
        for formula in (
            theorem_exports.get("tdfol_formulas")
            or bundle.get("tdfol_formulas")
            or bundle.get("tdfol_preview")
            or []
        )
        if str(formula).strip()
    ]
    dcec_formulas = [
        str(formula).strip()
        for formula in (
            theorem_exports.get("dcec_formulas")
            or bundle.get("dcec_formulas")
            or bundle.get("dcec_preview")
            or []
        )
        if str(formula).strip()
    ]
    theorem_exports["tdfol_formulas"] = tdfol_formulas
    theorem_exports["dcec_formulas"] = dcec_formulas
    theorem_exports.setdefault("tdfol_preview", tdfol_formulas[:3])
    theorem_exports.setdefault("dcec_preview", dcec_formulas[:3])
    theorem_exports["tdfol_formula_count"] = len(tdfol_formulas)
    theorem_exports["dcec_formula_count"] = len(dcec_formulas)
    theorem_export_metadata = theorem_exports.get("theorem_export_metadata")
    if not isinstance(theorem_export_metadata, dict):
        theorem_export_metadata = {}
        theorem_exports["theorem_export_metadata"] = theorem_export_metadata
    if proof_bundle_id and not theorem_export_metadata.get("proof_bundle_id"):
        theorem_export_metadata["proof_bundle_id"] = proof_bundle_id
    bundle.setdefault("contract_version", "claim_support_temporal_proof_bundle_v1")
    if proof_bundle_id:
        bundle.setdefault("persistence_key", proof_bundle_id)
    digest_payload = {
        "contract_version": bundle.get("contract_version"),
        "proof_bundle_id": proof_bundle_id,
        "claim_type": bundle.get("claim_type"),
        "claim_element_id": bundle.get("claim_element_id"),
        "rule_frame_id": bundle.get("rule_frame_id"),
        "temporal_fact_ids": bundle.get("temporal_fact_ids") or bundle.get("fact_ids") or [],
        "temporal_relation_ids": bundle.get("temporal_relation_ids") or bundle.get("relation_ids") or [],
        "temporal_issue_ids": bundle.get("temporal_issue_ids") or bundle.get("issue_ids") or [],
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "theorem_export_metadata": theorem_export_metadata,
    }
    bundle.setdefault("bundle_digest", _stable_payload_digest(digest_payload))
    return bundle


def _build_temporal_reasoning_payload(
    predicates: Iterable[Dict[str, Any]],
    *,
    claim_support_temporal_handoff: Any = None,
    claim_reasoning_review: Any = None,
    proof_bundles: Any = None,
) -> Dict[str, Any]:
    predicate_list: List[Dict[str, Any]] = [
        predicate for predicate in predicates
        if isinstance(predicate, dict)
    ]
    claim_elements: List[Dict[str, Any]] = []
    support_traces: List[Dict[str, Any]] = []
    timeline_events: List[Dict[str, Any]] = []
    temporal_proof_leads: List[Dict[str, Any]] = []
    temporal_relations: List[Dict[str, Any]] = []
    contradiction_signals: List[Dict[str, Any]] = []
    tdfol_formulas: List[str] = []
    dcec_formulas: List[str] = []
    claim_type_counts: Counter[str] = Counter()

    for predicate in predicate_list:
        claim_type = str(predicate.get("claim_type") or "").strip()
        if claim_type:
            claim_type_counts[claim_type] += 1

        predicate_type = str(predicate.get("predicate_type") or "").strip()
        if predicate_type == "claim_element":
            claim_symbol = _normalize_logic_symbol(predicate.get("claim_element_id") or predicate.get("predicate_id"), prefix="claim")
            claim_element = {
                "claim_symbol": claim_symbol,
                "claim_type": claim_type,
                "claim_element_id": predicate.get("claim_element_id"),
                "claim_element_text": predicate.get("claim_element_text"),
                "coverage_status": predicate.get("coverage_status"),
            }
            if isinstance(predicate.get("fact_registry_summary"), dict):
                claim_element["fact_registry_summary"] = dict(predicate["fact_registry_summary"])
            support_facts = [fact for fact in predicate.get("support_facts", []) or [] if isinstance(fact, dict)]
            if support_facts:
                claim_element["support_fact_count"] = len(support_facts)
            claim_elements.append(claim_element)
        elif predicate_type == "support_trace":
            trace_symbol = _normalize_logic_symbol(predicate.get("predicate_id") or predicate.get("support_ref"), prefix="support")
            support_trace = {
                "support_symbol": trace_symbol,
                "claim_type": claim_type,
                "support_ref": predicate.get("support_ref"),
                "support_kind": predicate.get("support_kind"),
                "text": predicate.get("text") or "",
            }
            for field in (
                "source_family",
                "source_record_id",
                "source_ref",
                "record_scope",
                "artifact_family",
                "corpus_family",
                "content_origin",
                "parse_source",
                "input_format",
                "quality_tier",
                "quality_score",
                "chunk_id",
                "chunk_index",
                "source_passage",
            ):
                value = predicate.get(field)
                if value not in (None, "", [], {}):
                    support_trace[field] = value
            support_traces.append(support_trace)
            claim_symbol = _normalize_logic_symbol(predicate.get("claim_element_id") or claim_type, prefix="claim")
            tdfol_formulas.append(f"Supports({trace_symbol},{claim_symbol})")
            dcec_formulas.append(f"Supports({trace_symbol},{claim_symbol})")
        elif predicate_type == "temporal_fact":
            event_symbol = _normalize_logic_symbol(predicate.get("fact_id") or predicate.get("predicate_id"), prefix="event")
            event_entry = {
                "event_symbol": event_symbol,
                "claim_type": claim_type,
                "fact_id": predicate.get("fact_id"),
                "text": predicate.get("text") or "",
                "fact_type": predicate.get("fact_type"),
                "start_date": predicate.get("start_date"),
                "end_date": predicate.get("end_date"),
                "granularity": predicate.get("granularity"),
                "is_approximate": bool(predicate.get("is_approximate", False)),
                "is_range": bool(predicate.get("is_range", False)),
                "relative_markers": list(predicate.get("relative_markers", []) or []),
            }
            timeline_events.append(event_entry)
            formulas = _build_temporal_formula_for_fact(event_symbol, event_entry)
            tdfol_formulas.append(formulas["tdfol"])
            dcec_formulas.append(formulas["dcec"])
        elif predicate_type == "temporal_proof_lead":
            lead_symbol = _normalize_logic_symbol(predicate.get("lead_id") or predicate.get("predicate_id"), prefix="lead")
            lead_entry = {
                "lead_symbol": lead_symbol,
                "claim_type": claim_type,
                "lead_id": predicate.get("lead_id"),
                "description": predicate.get("description") or "",
                "related_fact_ids": list(predicate.get("related_fact_ids", []) or []),
                "element_targets": list(predicate.get("element_targets", []) or []),
                "temporal_scope": predicate.get("temporal_scope"),
                "start_date": predicate.get("start_date"),
                "end_date": predicate.get("end_date"),
                "granularity": predicate.get("granularity"),
                "is_approximate": bool(predicate.get("is_approximate", False)),
                "is_range": bool(predicate.get("is_range", False)),
            }
            temporal_proof_leads.append(lead_entry)
            formulas = _build_temporal_formula_for_fact(lead_symbol, lead_entry)
            tdfol_formulas.append(formulas["tdfol"].replace("Fact", "EvidenceLead"))
            dcec_formulas.append(formulas["dcec"].replace("Happens", "Available").replace("HoldsDuring", "AvailableDuring"))
            for related_fact_id in lead_entry["related_fact_ids"]:
                event_symbol = _normalize_logic_symbol(related_fact_id, prefix="event")
                tdfol_formulas.append(f"Supports({lead_symbol},{event_symbol})")
                dcec_formulas.append(f"Supports({lead_symbol},{event_symbol})")
        elif predicate_type == "temporal_relation":
            relation_type = str(predicate.get("relation_type") or "related_to").strip().lower() or "related_to"
            source_symbol = _normalize_logic_symbol(predicate.get("source_fact_id"), prefix="event")
            target_symbol = _normalize_logic_symbol(predicate.get("target_fact_id"), prefix="event")
            temporal_relations.append(
                {
                    "relation_id": predicate.get("predicate_id"),
                    "claim_type": claim_type,
                    "relation_type": relation_type,
                    "source_event_symbol": source_symbol,
                    "target_event_symbol": target_symbol,
                    "source_fact_id": predicate.get("source_fact_id"),
                    "target_fact_id": predicate.get("target_fact_id"),
                    "confidence": predicate.get("confidence"),
                }
            )
            relation_name = {
                "before": "Before",
                "same_time": "SameTime",
                "overlaps": "Overlaps",
            }.get(relation_type, _normalize_logic_symbol(relation_type, prefix="rel").title().replace("_", ""))
            tdfol_formulas.append(f"{relation_name}({source_symbol},{target_symbol})")
            dcec_formulas.append(f"{relation_name}({source_symbol},{target_symbol})")
        elif predicate_type in {"temporal_issue", "contradiction_candidate"}:
            signal_symbol = _normalize_logic_symbol(predicate.get("predicate_id") or predicate.get("summary"), prefix="signal")
            signal_entry = {
                "signal_symbol": signal_symbol,
                "claim_type": claim_type,
                "predicate_type": predicate_type,
                "issue_type": predicate.get("issue_type") or predicate.get("summary") or predicate_type,
                "summary": predicate.get("summary") or "",
                "severity": predicate.get("severity"),
            }
            contradiction_signals.append(signal_entry)
            if predicate_type == "temporal_issue":
                left_symbol = _normalize_logic_symbol(predicate.get("left_node_name"), prefix="event")
                right_symbol = _normalize_logic_symbol(predicate.get("right_node_name"), prefix="event")
                tdfol_formulas.append(f"Conflict({left_symbol},{right_symbol})")
                dcec_formulas.append(f"Conflicts({left_symbol},{right_symbol})")

    temporal_reasoning_payload = {
        "formalism": "tdfol_dcec_bridge_v1",
        "claim_types": sorted(claim_type_counts.keys()),
        "claim_elements": claim_elements,
        "support_traces": support_traces,
        "timeline_events": timeline_events,
        "temporal_proof_leads": temporal_proof_leads,
        "temporal_relations": temporal_relations,
        "contradiction_signals": contradiction_signals,
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "tdfol_formula_count": len(tdfol_formulas),
        "dcec_formula_count": len(dcec_formulas),
    }
    normalized_proof_bundles = _normalize_proof_bundles(proof_bundles)
    if normalized_proof_bundles:
        bundle_formula_payload = _extract_formula_payload_from_proof_bundles(normalized_proof_bundles)
        if bundle_formula_payload["tdfol_formulas"] or bundle_formula_payload["dcec_formulas"]:
            temporal_reasoning_payload["tdfol_formulas"] = bundle_formula_payload["tdfol_formulas"]
            temporal_reasoning_payload["dcec_formulas"] = bundle_formula_payload["dcec_formulas"]
            temporal_reasoning_payload["tdfol_formula_count"] = len(bundle_formula_payload["tdfol_formulas"])
            temporal_reasoning_payload["dcec_formula_count"] = len(bundle_formula_payload["dcec_formulas"])
            temporal_reasoning_payload["tdfol_formula_certainties"] = bundle_formula_payload["tdfol_formula_certainties"]
            temporal_reasoning_payload["dcec_formula_certainties"] = bundle_formula_payload["dcec_formula_certainties"]
        temporal_reasoning_payload["proof_bundles"] = deepcopy(normalized_proof_bundles)
        temporal_reasoning_payload["proof_execution_source"] = "temporal_proof_bundle"
        if bundle_formula_payload["theorem_export_metadata"]:
            temporal_reasoning_payload["theorem_export_metadata"] = bundle_formula_payload["theorem_export_metadata"]
    normalized_handoff = _normalize_claim_support_temporal_handoff(claim_support_temporal_handoff)
    if normalized_handoff:
        temporal_reasoning_payload["claim_support_temporal_handoff"] = normalized_handoff
        handoff_export_metadata = _build_theorem_export_metadata(normalized_handoff)
        existing_export_metadata = (
            temporal_reasoning_payload.get("theorem_export_metadata")
            if isinstance(temporal_reasoning_payload.get("theorem_export_metadata"), dict)
            else {}
        )
        if existing_export_metadata:
            merged_export_metadata = dict(handoff_export_metadata)
            merged_export_metadata.update(existing_export_metadata)
            temporal_reasoning_payload["theorem_export_metadata"] = merged_export_metadata
        else:
            temporal_reasoning_payload["theorem_export_metadata"] = handoff_export_metadata
    normalized_claim_reasoning_review = _normalize_claim_reasoning_review(claim_reasoning_review)
    if normalized_claim_reasoning_review:
        temporal_reasoning_payload["claim_reasoning_review"] = normalized_claim_reasoning_review
    return temporal_reasoning_payload


def _temporal_input_reason(payload: Mapping[str, Any]) -> str:
    """Bound the finite local graph input before copying records or importing."""
    if len(payload) > 128:
        return "authority_field_bound_exceeded"
    containers = [payload]
    for key in ("metadata", "provenance", "applicable_date", "date_context", "temporal_window"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            if len(nested) > 64:
                return "authority_field_bound_exceeded"
            containers.append(nested)
    for container in containers:
        for key in ("source_text", "text", "rule_text"):
            value = container.get(key)
            if isinstance(value, str) and len(value) > _TEMPORAL_MAX_TEXT:
                return "source_text_bound_exceeded"
        for key in ("authority_id", "authority_identity", "id", "citation", "cite", "jurisdiction",
                    "authority_version", "version", "corpus_version", "release"):
            value = container.get(key)
            if isinstance(value, str) and len(value) > 1024:
                return "authority_field_bound_exceeded"
    window = payload.get("temporal_window")
    if isinstance(window, Mapping) and any(not isinstance(value, (str, type(None)))
                                          or isinstance(value, str) and len(value) > 64 for value in window.values()):
        return "temporal_record_bound_exceeded"
    for key, limit in (("law_versions", _TEMPORAL_MAX_VERSIONS),
                       ("changes", _TEMPORAL_MAX_CHANGES), ("temporal_changes", _TEMPORAL_MAX_CHANGES)):
        records = payload.get(key)
        if records in (None, []):
            continue
        if not isinstance(records, list) or len(records) > limit:
            return "temporal_records_bound_exceeded"
        for record in records:
            if not isinstance(record, Mapping) or len(record) > 64:
                return "malformed_temporal_record"
            for value in record.values():
                values = value.values() if isinstance(value, Mapping) else value if isinstance(value, (list, tuple)) else (value,)
                if isinstance(value, (Mapping, list, tuple)) and len(value) > 32:
                    return "temporal_record_bound_exceeded"
                if any(not isinstance(item, (str, int, float, bool, type(None)))
                       or isinstance(item, str) and len(item) > 4096 for item in values):
                    return "temporal_record_bound_exceeded"
    return ""


def _temporal_authority_api() -> Tuple[Any, str]:
    """Load LegalIR temporal graph and query APIs only when a caller needs them."""
    module, error = import_module_optional(_TEMPORAL_AUTHORITY_MODULE)
    required = (
        "build_legal_ir_temporal_authority_graph",
        "query_legal_ir_temporal_applicability",
        "LegalIRTemporalQueryContext",
    )
    if module is None or any(not hasattr(module, name) for name in required):
        return None, _provider_diagnostic(error, fallback="temporal_authority_api_unavailable")
    return module, ""


def _unavailable_temporal_applicability(reason: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contract": _TEMPORAL_APPLICABILITY_CONTRACT,
        "available": False,
        "applicable": False,
        "applicability_status": "unavailable",
        "legal_ir_status": "unavailable",
        "reason": reason,
        "review_reason": f"temporal_applicability_{reason}",
        "guessed_current_rule": False,
        "selected_current_rule": False,
        "query_date_source": "unavailable",
        "decisions": [],
        "version_decisions": [],
        "diagnostics": [],
        "api": _TEMPORAL_AUTHORITY_MODULE,
    }
    payload.update(extra)
    return payload


def _label_temporal_status(legal_ir_status: str, law: Any) -> str:
    label = _TEMPORAL_STATUS_LABELS.get(legal_ir_status, legal_ir_status or "unavailable")
    amended_by = tuple(getattr(law, "amended_by", ()) or ())
    if legal_ir_status == "superseded" and amended_by:
        return "amended"
    return label


def evaluate_temporal_requirement_applicability(
    authority: Mapping[str, Any],
    query_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Decide applicability with LegalIR's temporal graph and query context.

    An unknown source version or query date stays ``unavailable``. This function
    does not substitute today's date or another version and call it current.
    """
    if not isinstance(authority, Mapping) or len(authority) > 128:
        return _unavailable_temporal_applicability("authority_field_bound_exceeded")
    payload = _as_mapping(authority)
    if query_context is not None and (not isinstance(query_context, Mapping) or len(query_context) > 32):
        return _unavailable_temporal_applicability("malformed_query_context")
    reason = _temporal_input_reason(payload)
    if reason:
        return _unavailable_temporal_applicability(reason)
    context = dict(query_context or {})
    nested_query = payload.get("query_context") or payload.get("temporal_query_context")
    if isinstance(nested_query, Mapping):
        if len(nested_query) > 32:
            return _unavailable_temporal_applicability("query_context_bound_exceeded")
        merged = dict(nested_query)
        merged.update(context)
        context = merged
    if len(context) > 32 or any(not isinstance(value, (str, int, float, bool, type(None)))
                                or isinstance(value, str) and len(value) > 1024 for value in context.values()):
        return _unavailable_temporal_applicability("query_context_bound_exceeded")
    coordinates = _authority_coordinates(payload)
    source_jurisdiction = str(coordinates.get("jurisdiction") or "")
    if not _known_token(source_jurisdiction) or not _known_token(str(context.get("jurisdiction") or source_jurisdiction)):
        return _unavailable_temporal_applicability("unknown_source_jurisdiction")
    version = str(coordinates.get("authority_version") or "")
    requested_version = str(context.get("authority_version") or context.get("version") or version)
    if not _known_token(version) or not _known_token(requested_version):
        return _unavailable_temporal_applicability("unknown_source_version", authority_version=version)
    if requested_version != version:
        return _unavailable_temporal_applicability("source_version_mismatch", authority_version=version)
    explicit_version_id = str(context.get("law_version_id") or payload.get("law_version_id") or "")
    versions = _selected_law_versions(payload, coordinates)
    matched = [item for item in versions
               if isinstance(item.get("version"), str) and item["version"] == version
               and (not explicit_version_id or str(item.get("law_version_id") or "") == explicit_version_id)]
    if len(matched) != 1:
        return _unavailable_temporal_applicability(
            "unknown_source_version" if not matched else "ambiguous_source_version", authority_version=version)
    selected_version = matched[0]
    if any(selected_version.get(key) and coordinates.get(key)
           and str(selected_version[key]) != str(coordinates[key]) for key in ("authority_id", "jurisdiction")):
        return _unavailable_temporal_applicability("source_identity_mismatch", authority_version=version)
    known_ids = [str(item.get("law_version_id") or "") for item in versions if item.get("law_version_id")]
    if len(known_ids) != len(set(known_ids)):
        return _unavailable_temporal_applicability("ambiguous_source_version", authority_version=version)
    effective, reason = _date_aliases(selected_version, ("effective_date", "effective_on"))
    if reason or not effective:
        return _unavailable_temporal_applicability(reason or "unknown_source_date", authority_version=version)
    source_effective, reason = _source_date_aliases(payload, ("effective_date", "effective_on"))
    if reason or source_effective and source_effective != effective:
        return _unavailable_temporal_applicability(reason or "contradictory_date_context", authority_version=version)
    for item in versions:
        for keys in (("effective_date", "effective_on"), ("sunset_date", "sunsets_on", "expiration_date"),
                     ("repeal_date", "repealed_on"), ("superseded_date", "superseded_on"),
                     ("emergency_expires_on", "emergency_expiration_date")):
            value, reason = _date_aliases(item, keys)
            if reason:
                return _unavailable_temporal_applicability(reason, authority_version=version)
            if value and keys[0] != "effective_date" and value <= effective and item is selected_version:
                return _unavailable_temporal_applicability("contradictory_date_context", authority_version=version)
            if value:
                item[keys[0]] = value
    for keys in (("sunset_date", "expiration_date"), ("repeal_date",), ("superseded_date",)):
        source_end, reason = _source_date_aliases(payload, keys)
        selected_end, selected_reason = _date_aliases(selected_version, keys)
        if reason or selected_reason or source_end and selected_end and source_end != selected_end:
            return _unavailable_temporal_applicability(reason or selected_reason or "contradictory_date_context", authority_version=version)
        if source_end and not selected_end:
            if source_end <= effective:
                return _unavailable_temporal_applicability("contradictory_date_context", authority_version=version)
            selected_version[keys[0]] = source_end
    for change in payload.get("changes") or payload.get("temporal_changes") or []:
        for keys in (("effective_date", "effective_on"), ("enacted_date", "enacted_on")):
            _value, reason = _date_aliases(change, keys)
            if reason:
                return _unavailable_temporal_applicability(reason, authority_version=version)
    query_keys = ("query_date", "as_of", "as_of_date")
    query_date, reason = _date_aliases(context, query_keys)
    if not query_date and not reason:
        query_date, reason = _source_date_aliases(payload, ("as_of_date", "applicable_date", "applicable_on"))
    if reason or not query_date:
        return _unavailable_temporal_applicability(reason or "unknown_source_date", authority_version=version)
    query_date_source = "explicit_query_context" if any(context.get(key) for key in query_keys) else "as_of_date"
    try:
        module, error = _temporal_authority_api()
        if module is None:
            return _unavailable_temporal_applicability(
                "temporal_authority_api_unavailable",
                authority_version=version,
                query_date=query_date,
                diagnostic="temporal_authority_api_unavailable",
            )
        authority_id = str(
            (selected_version or {}).get("authority_id")
            or coordinates.get("authority_id")
            or ""
        )
        jurisdiction = str((selected_version or {}).get("jurisdiction") or coordinates.get("jurisdiction") or "")
        query_jurisdiction = str(context.get("jurisdiction") or jurisdiction)
        law_versions = []
        for item in versions:
            law = dict(item)
            law.setdefault("authority_id", authority_id)
            law.setdefault("jurisdiction", jurisdiction)
            law.setdefault("citation", str(coordinates.get("citation") or ""))
            if not str(law.get("law_version_id") or "").strip():
                law["law_version_id"] = f"{law['authority_id']}:{law.get('version') or 'unspecified'}"
            law_versions.append(law)
        if not selected_version:
            return _unavailable_temporal_applicability(
                "unknown_source_version",
                authority_version=version,
                query_date=query_date,
                known_versions=[str(item.get("version") or "") for item in versions],
            )
        selected_id = str(selected_version.get("law_version_id") or f"{authority_id}:{version}")
        changes = payload.get("changes") or payload.get("temporal_changes") or []
        document = {
            "document_id": authority_id or "legal-requirement",
            "authority_id": authority_id,
            "jurisdiction": jurisdiction,
            "version": version,
            "law_versions": law_versions,
            "changes": list(changes) if isinstance(changes, list) else [],
        }
        graph = module.build_legal_ir_temporal_authority_graph(document)
        query = module.LegalIRTemporalQueryContext(
            query_date=query_date,
            jurisdiction=query_jurisdiction,
            authority_id=authority_id,
            law_version_ids=(selected_id,),
        )
        result = module.query_legal_ir_temporal_applicability(graph, query)
        result_dict = result.to_dict()
        decisions = list(result_dict.get("decisions") or [])
        decision = next((item for item in decisions if item.get("law_version_id") == selected_id), None)
        if decision is None:
            return _unavailable_temporal_applicability(
                "temporal_applicability_unresolved",
                authority_version=version,
                query_date=query_date,
                query_date_source=query_date_source,
                query_jurisdiction=query_jurisdiction,
                diagnostics=list(result_dict.get("diagnostics") or []),
                guessed_current_rule=False,
            )
        law = graph.law_version_by_id.get(str(decision.get("law_version_id") or ""))
        legal_ir_status = str(decision.get("status") or "unavailable")
        label = _label_temporal_status(legal_ir_status, law)
        applicable = legal_ir_status == "applicable" and label == "effective"
        return {
            "contract": _TEMPORAL_APPLICABILITY_CONTRACT,
            "available": True,
            "applicable": applicable,
            "applicability_status": label,
            "legal_ir_status": legal_ir_status,
            "reason": "" if applicable else f"temporal_applicability_{label}",
            "review_reason": "" if applicable else f"temporal_applicability_{label}",
            "guessed_current_rule": False,
            "selected_current_rule": False,
            "query_date": query_date,
            "query_date_source": query_date_source,
            "query_jurisdiction": query_jurisdiction,
            "authority_version": str(getattr(law, "version", "") or version),
            "law_version_id": str(decision.get("law_version_id") or ""),
            "effective_date": str(decision.get("effective_date") or ""),
            "end_date": str(decision.get("end_date") or ""),
            "amended_by": list(getattr(law, "amended_by", ()) or ()),
            "superseded_by": str(getattr(law, "superseded_by", "") or ""),
            "repealed_by": str(getattr(law, "repealed_by", "") or ""),
            "decisions": decisions,
            "version_decisions": decisions,
            "diagnostics": list(decision.get("diagnostics") or []),
            "schema_version": result_dict.get("schema_version") or "",
            "api": _TEMPORAL_AUTHORITY_MODULE,
            "temporal_authority_graph_id": graph.temporal_authority_graph_id,
        }
    except Exception:
        return _unavailable_temporal_applicability(
            "temporal_authority_evaluation_failed", authority_version=version,
            query_date=query_date, diagnostic="legal_ir_temporal_api_failure")


from . import logic as _logic_owner


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


_MOVED = (
    "_build_temporal_reasoning_payload",
    "evaluate_temporal_requirement_applicability",
    "_normalize_temporal_proof_bundle",
    "_normalize_claim_support_temporal_handoff",
    "_temporal_input_reason",
    "_build_temporal_formula_for_fact",
    "_unavailable_temporal_applicability",
    "_temporal_authority_api",
    "_label_temporal_status",
)

for _name in _MOVED:
    _fn = _bind_to_owner_globals(globals()[_name])
    globals()[_name] = _fn
    setattr(_logic_owner, _name, _fn)
