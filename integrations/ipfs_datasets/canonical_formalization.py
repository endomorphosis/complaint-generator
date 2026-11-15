"""Canonical formalization moved out of the datasets logic owner.

The moved functions keep their original signatures and bodies. Helpers that
remain on the owner are imported after those helpers are bound.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import types
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def extract_source_bound_rule_candidates(authority: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract rule candidates from authority text and promote only exact matches.

    Promotion keeps jurisdiction, authority identity and version, the checked
    source hash, the exact UTF-8 span, and an applicable ISO date. Keyword
    templates, missing coordinates, and ambiguous structure stay candidates.
    Caller-supplied promoted or applicable flags are ignored.
    """
    if isinstance(authority, Mapping) and len(authority) > 128:
        return _unavailable_rule_candidates("authority_field_bound_exceeded")
    payload = _as_mapping(authority)
    reason = _temporal_input_reason(payload)
    if reason:
        return _unavailable_rule_candidates(reason)
    legacy_template = (
        payload.get("legacy_template") is True
        or payload.get("verification_status") == "unverified_template"
        or payload.get("template_kind") in {"claim_keyword_template", "procedural_template"}
    )
    coordinates = _authority_coordinates(payload)
    source_text = str(coordinates["source_text"] or "")
    sentences = _iter_rule_sentences(source_text) if source_text else []
    if len(sentences) > _TEMPORAL_MAX_RULES:
        return _unavailable_rule_candidates("rule_count_bound_exceeded")
    temporal = evaluate_temporal_requirement_applicability(payload)
    treatment = requirement_treatment_support(payload)
    explicit_rule = _first_text(payload, "rule_text")
    selected: List[Tuple[str, Optional[Dict[str, Any]], str]] = []
    if explicit_rule:
        span, status = _unique_fragment_span(source_text, explicit_rule)
        supplied_span = payload.get("source_span") if isinstance(payload.get("source_span"), Mapping) else None
        if span and supplied_span:
            try:
                supplied_start = int(supplied_span.get("start"))
                supplied_end = int(supplied_span.get("end"))
            except (TypeError, ValueError):
                supplied_start = supplied_end = None
            if supplied_start != span["start"] or supplied_end != span["end"]:
                span = None
                status = "source_span_mismatch"
        selected.append((explicit_rule, span, status))
    elif sentences:
        seen: Dict[str, int] = {}
        for sentence, char_start, char_end in sentences:
            seen[sentence] = seen.get(sentence, 0) + 1
            byte_start, byte_end = _byte_span(source_text, char_start, char_end)
            if seen[sentence] > 1:
                selected.append((sentence, None, "ambiguous_source_span"))
                continue
            span = {
                "start": byte_start,
                "end": byte_end,
                "text": sentence,
                "unit": "utf-8-bytes",
            }
            if source_text.find(sentence) != char_start:
                # An earlier identical sentence makes this occurrence ambiguous.
                selected.append((sentence, None, "ambiguous_source_span"))
            else:
                selected.append((sentence, span, ""))
        # Mark the first copy ambiguous once a later copy was seen.
        ambiguous_texts = {text for text, _span, status in selected if status == "ambiguous_source_span"}
        if ambiguous_texts:
            rewritten: List[Tuple[str, Optional[Dict[str, Any]], str]] = []
            seen_text: set[str] = set()
            for item in selected:
                text = item[0]
                if text in seen_text:
                    continue
                seen_text.add(text)
                if text in ambiguous_texts:
                    rewritten.append((text, None, "ambiguous_source_span"))
                else:
                    rewritten.append(item)
            selected = rewritten
    else:
        selected.append(("", None, "missing_source_text"))

    empty_structure = {
        "conditions": [],
        "exceptions": [],
        "connective": "none",
        "conjunction_count": 0,
        "disjunction_count": 0,
        "conjuncts": [],
        "disjuncts": [],
        "rule_character": "unknown",
        "deontic_operator": "unknown",
        "deontic_operator_source": "pattern_heuristic",
        "deontic_operator_is_proof": False,
        "entailment_status": "unsupported",
    }
    candidates = [
        _candidate_record(
            authority=payload,
            temporal=temporal, treatment=treatment,
            coordinates=coordinates,
            sentence=sentence,
            span=span,
            span_status=status or "missing_source_span",
            structure=_structure_for_sentence(source_text, sentence) if sentence else empty_structure,
            legacy_template=legacy_template,
        )
        for sentence, span, status in selected
        if sentence or not any(item[0] for item in selected)
    ]
    if not candidates:
        candidates = [
            _candidate_record(
                authority=payload,
                temporal=temporal, treatment=treatment,
                coordinates=coordinates,
                sentence="",
                span=None,
                span_status="missing_source_text",
                structure={
                    "conditions": [], "exceptions": [], "connective": "none",
                    "conjunction_count": 0, "disjunction_count": 0, "conjuncts": [], "disjuncts": [],
                    "rule_character": "unknown", "deontic_operator": "unknown",
                    "deontic_operator_source": "pattern_heuristic", "deontic_operator_is_proof": False,
                    "entailment_status": "unsupported",
                },
                legacy_template=legacy_template,
            )
        ]
    promoted = [dict(candidate) for candidate in candidates if candidate["promoted"]]
    return {
        "contract": SOURCE_BOUND_RULE_CONTRACT,
        "candidates": candidates,
        "promoted_requirements": promoted,
        "candidate_count": len(candidates),
        "promoted_count": len(promoted),
    }


def _bridge_canonical_source_map(
    *,
    source_text: str,
    source_cid: str,
    citation: str,
    entries: Sequence[Any],
    rules: Sequence[Any],
    stages: Sequence[Any],
    identities: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bridge canonical character spans into the LegalIR source-map schema."""

    source_maps = _canonical_source_map_module
    builder = source_maps.LegalIRSourceMapBuilder(
        source_map_id="",
        metadata={
            "builder": "canonical_compiler_adapter",
            "span_unit": "character",
            "schema_version": identities.get("source_map_schema"),
            "compiler_interface": identities.get("compiler_interface"),
            "pipeline_cid": identities.get("pipeline_cid"),
        },
    )
    builder.add_source_document(
        source_cid,
        source_text,
        citation=citation,
        metadata={"source_cid": source_cid, "span_unit": "character"},
    )
    formula_ids = list(dict.fromkeys(str(rule.rule_cid) for rule in rules))
    expected_fields = {
        (str(rule.rule_cid), f"/rules/{index}/{field}")
        for index, rule in enumerate(rules)
        for field in rule.to_dict()
    }
    observed_fields = Counter((str(entry.rule_cid), str(entry.field_path)) for entry in entries)
    coverage_issues = []
    if set(observed_fields) != expected_fields or any(count != 1 for count in observed_fields.values()):
        coverage_issues.append({
            "code": "canonical_field_coverage_mismatch",
            "message": "Every emitted rule field requires exactly one matching source-map entry.",
            "field_path": "source_map",
        })
    field_ids_by_rule: Dict[str, List[str]] = {}
    passages: List[Dict[str, Any]] = []
    for entry in entries:
        passage = source_text[entry.start:entry.end]
        span = builder.add_span(
            source_cid,
            entry.start,
            entry.end,
            citation=citation,
            normalized_text=passage,
            transformation_step_id="canonical.source_span",
            decompiler_attribution="not_decompiled",
            metadata={
                "rule_cid": entry.rule_cid,
                "field_path": entry.field_path,
                "attribution": entry.attribution,
                "span_unit": "character",
            },
        )
        node_id = f"field:{entry.rule_cid}:{entry.field_path}"
        builder.add_node(
            node_id,
            node_kind="canonical_field",
            span_ids=(span.span_id,),
            emitted_fact=entry.rule_cid,
            transformation_step_id="canonical.source_span",
            decompiler_attribution="not_decompiled",
            metadata={"field_path": entry.field_path, "rule_cid": entry.rule_cid},
        )
        field_ids_by_rule.setdefault(str(entry.rule_cid), []).append(node_id)
        passages.append(
            {
                "rule_cid": entry.rule_cid,
                "field_path": entry.field_path,
                "source_cid": entry.source_cid,
                "start": entry.start,
                "end": entry.end,
                "passage": passage,
                "span_id": span.span_id,
                "span_unit": "character",
            }
        )

    for rule in rules:
        rule_cid = str(rule.rule_cid)
        parents = tuple(field_ids_by_rule.get(rule_cid) or ())
        if not parents:
            continue
        builder.add_derived_node(
            rule_cid,
            node_kind="compiler_formula",
            derived_from_node_ids=parents,
            transformation_step="compiler.emit_formula",
            transform_kind=source_maps.LegalIRTransformationKind.COMPILER,
            emitted_fact=rule_cid,
            decompiler_attribution="not_decompiled",
            metadata={"rule": _jsonable(rule.to_dict())},
        )

    previous = tuple(node_id for ids in field_ids_by_rule.values() for node_id in ids)
    stage_ids: List[str] = []
    for stage in stages:
        stage_id = str(stage.stage_id)
        node_id = f"stage:{stage_id}"
        builder.add_derived_node(
            node_id,
            node_kind="compiler_stage",
            derived_from_node_ids=previous or tuple(formula_ids),
            transformation_step=f"compiler.stage.{stage_id}",
            transform_kind=source_maps.LegalIRTransformationKind.COMPILER,
            emitted_fact=node_id,
            decompiler_attribution="not_decompiled",
            metadata={
                "interface": str(stage.interface),
                "identity_cid": str(stage.identity_cid),
                "status": str(stage.status),
            },
        )
        previous = (node_id,)
        stage_ids.append(node_id)

    bridged = builder.to_source_map()
    formula_document = {
        "modal_ir": {
            "document_id": source_cid,
            "normalized_text": source_text,
            "citation": citation,
            "formulas": [
                {
                    "formula_id": item["rule_cid"],
                    "provenance": {
                        "source_document_id": source_cid,
                        "source_id": source_cid,
                        "citation": citation,
                        "start_char": item["start"],
                        "end_char": item["end"],
                        "transformation_step": "compiler.source_span",
                        "decompiler_attribution": "not_decompiled",
                    },
                }
                for item in passages
            ],
        }
    }
    built = source_maps.build_legal_ir_source_map(formula_document)
    if (bridged.schema_version != identities.get("source_map_schema")
            or built.schema_version != identities.get("source_map_schema")):
        coverage_issues.append({
            "code": "source_map_schema_mismatch",
            "message": "The executed source-map schema differs from the current identity.",
            "field_path": "source_map.schema_version",
        })
    validation = source_maps.validate_legal_ir_source_map(bridged)
    built_validation = source_maps.validate_legal_ir_source_map(built)
    emitted_ids = tuple(dict.fromkeys([*formula_ids, *stage_ids]))
    binding = source_maps.bind_legal_ir_artifact_source_map(
        {"emitted_fact_ids": list(emitted_ids), "artifact_id": bridged.source_map_id},
        bridged,
        artifact_kind="compiler_formula",
        emitted_fact_ids=emitted_ids,
    )
    binding_payload = {
        "artifact_id": binding.artifact_id,
        "artifact_kind": binding.artifact_kind,
        "emitted_fact_ids": list(binding.emitted_fact_ids),
        "traceable_fact_ids": list(binding.traceable_fact_ids),
        "derived_fact_ids": list(binding.derived_fact_ids),
        "missing_fact_ids": list(binding.missing_fact_ids),
        "traceable": bool(binding.traceable),
        "issues": [issue.to_dict() for issue in binding.issues],
    }
    traces = [
        source_maps.trace_legal_ir_fact(bridged, fact_id).to_dict()
        for fact_id in emitted_ids
    ]
    built_formula_ids = [node.node_id for node in built.nodes]
    missing_from_build = sorted(set(formula_ids) - set(built_formula_ids))
    transformations_missing = [
        trace["fact_id"]
        for trace in traces
        if trace["fact_id"] in formula_ids
        and (not trace.get("transformation_steps") or not trace.get("source_spans"))
    ]
    coverage_ok = bool(formula_ids) and bool(stage_ids) and not missing_from_build and not coverage_issues
    return {
        "source_map": bridged.to_dict(),
        "built_source_map": built.to_dict(),
        "validation": validation.to_dict(),
        "built_validation": built_validation.to_dict(),
        "traceability": binding_payload,
        "traces": traces,
        "passages": passages,
        "formula_ids": formula_ids,
        "stage_node_ids": stage_ids,
        "transformations_missing": transformations_missing,
        "coverage_issues": coverage_issues,
        "coverage_ok": (
            coverage_ok
            and validation.valid
            and built_validation.valid
            and binding.traceable
            and not transformations_missing
            and binding.emitted_fact_ids
        ),
    }


def audit_canonical_formalization_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Recheck source/IR coverage and distinguish structure from execution.

    A serialized mapping can be structurally valid without proving that this
    process executed it. Only an unchanged originally stored receipt can retain
    executed capability, and only while its complete live identities still match.
    """
    if not _canonical_modules_ready():
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
        return {"status": "unavailable", "tampered": False,
                "capability": capability.as_dict(), "reason": capability.reason,
                "issues": [], "traceable": False}

    issues: List[Dict[str, str]] = []
    current = canonical_compiler_identities() or {}
    recorded = payload.get("identities") if isinstance(payload.get("identities"), Mapping) else {}
    identities_match = dict(recorded) == current
    if not identities_match:
        issues.append({"code": "canonical_identity_mismatch",
                       "message": "Receipt identities do not match the current canonical compiler contract.",
                       "field_path": "identities"})
    execution_origin = _canonical_receipt_has_execution_origin(payload)
    receipt_id = payload.get("receipt_id")
    known_origin = isinstance(receipt_id, str) and receipt_id in _CANONICAL_RECEIPT_ORIGIN_DIGESTS
    if known_origin and not execution_origin:
        issues.append({"code": "execution_receipt_mismatch",
                       "message": "Receipt differs from the originally stored execution record.",
                       "field_path": "receipt_id"})

    validation_payload = None
    traceable = False
    status_value = str(payload.get("status") or "")
    text = payload.get("source_text")
    if isinstance(text, str):
        for index, passage in enumerate(payload.get("passages") or ()):
            if not isinstance(passage, Mapping):
                issues.append({"code": "passage_invalid", "message": "Passage record is not an object.",
                               "field_path": f"passages[{index}]"})
                continue
            start, end = passage.get("start"), passage.get("end")
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text)):
                issues.append({"code": "character_span_out_of_range",
                               "message": "Stored passage is outside the source character length.",
                               "field_path": f"passages[{index}]"})
            elif text[start:end] != passage.get("passage"):
                issues.append({"code": "passage_tampered",
                               "message": "Stored passage does not match the source character span.",
                               "field_path": f"passages[{index}].passage"})
    if status_value in {"success", "partial"}:
        try:
            request = _canonical_contracts_module.CompilerRequest.from_dict(payload.get("compiler_request"))
            result = _canonical_contracts_module.CompilerResult.from_dict(payload.get("compiler_result"))
            if (request.request_cid != result.request_cid
                    or request.request_cid != payload.get("request_cid")
                    or request.source_cid != payload.get("source_cid")
                    or request.source_text != payload.get("source_text")
                    or str(result.result_cid) != payload.get("result_cid")):
                issues.append({"code": "source_or_result_binding_mismatch",
                               "message": "Top-level source and compiler result do not match their typed request.",
                               "field_path": "compiler_request"})
            expected_outcome = "partial" if result.unsupported_semantics else "success"
            if (str(getattr(result.status, "value", result.status)) != "success"
                    or result.canonical_ir is None or status_value != expected_outcome):
                issues.append({"code": "compiler_outcome_mismatch",
                               "message": "Receipt status does not match the executed compiler outcome.",
                               "field_path": "status"})
            provenance = result.provenance
            if any(provenance.get(key) != current.get(identity) for key, identity in (
                    ("measured_adapter_raw_cid", "measured_compiler_raw_cid"),
                    ("compiler_config_cid", "compiler_config_cid"),
                    ("policy_cid", "policy_cid"))):
                issues.append({"code": "compiler_provenance_mismatch",
                               "message": "Compiler provenance differs from the current measured implementation.",
                               "field_path": "compiler_result.provenance"})
            stages = []
            for item in payload.get("stages") or ():
                stage = _canonical_pipeline_module.CompilerStageRecord(
                    stage_id=item["stage_id"], interface=item["interface"],
                    input_cid=item["input_cid"], output_cid=item["output_cid"],
                    config_cid=item["config_cid"], status=item["status"],
                    unsupported=tuple(item.get("unsupported") or ()),
                )
                if stage.to_dict() != item:
                    raise ValueError("stage identity mismatch")
                stages.append(stage)
            if ([stage.stage_id for stage in stages] != current.get("stage_ids")
                    or payload.get("pipeline_cid") != current.get("pipeline_cid")):
                issues.append({"code": "pipeline_stage_identity_mismatch",
                               "message": "Receipt does not contain the current complete ordered pipeline.",
                               "field_path": "stages"})
            span_issues = _prevalidate_character_spans(
                request.source_text, request.source_cid, result.source_map)
            issues.extend(span_issues)
            if not span_issues and result.canonical_ir is not None:
                bridge = _bridge_canonical_source_map(
                    source_text=request.source_text, source_cid=request.source_cid,
                    citation=str(payload.get("citation") or ""),
                    entries=result.source_map, rules=result.canonical_ir.rules,
                    stages=stages, identities=current,
                )
                validation_payload = bridge["validation"]
                traceable = bool(bridge["coverage_ok"])
                issues.extend(bridge["coverage_issues"])
                # Rebuild both maps from the typed source/result. Neither a
                # caller's smaller formula list nor an internally consistent
                # map from a different document can select the checked universe.
                for field, key in (
                        ("formula_ids", "formula_ids"), ("passages", "passages"),
                        ("source_map", "source_map"), ("built_source_map", "built_source_map"),
                        ("source_map_validation", "validation"),
                        ("built_source_map_validation", "built_validation"),
                        ("traceability", "traceability"), ("traces", "traces")):
                    if payload.get(field) != bridge[key]:
                        issues.append({"code": "source_map_binding_mismatch",
                                       "message": "Stored map, passages or emitted IDs differ from the full typed result.",
                                       "field_path": field})
                if not traceable:
                    issues.append({"code": "traceability_failed",
                                   "message": "Every emitted formula must trace to its source and transformations.",
                                   "field_path": "formula_ids"})
        except Exception:
            # Malformed persisted records stay typed; parser/contract exception
            # text can contain the caller's source and must not become a report.
            issues.append({"code": "canonical_record_invalid",
                           "message": "Typed compiler request, result or pipeline record is invalid.",
                           "field_path": "compiler_result"})

    structurally_valid = status_value in {"success", "partial"} and not issues and traceable
    executed = structurally_valid and execution_origin
    reason = ("Canonical formalization receipt failed integrity checks." if issues else
              "" if executed else "Serialized structure does not prove an original compiler execution.")
    capability = classify_canonical_compiler_capability(_canonical_evidence(
        executed=executed, status=status_value if executed else "failed",
        traceable=structurally_valid, source_map_valid=structurally_valid,
        schema_match=identities_match, tampered=bool(issues), reason=reason,
    ))
    return {
        "schema_version": "canonical-formalization-audit/v1",
        "status": "tampered" if issues else "verified" if executed else "unverified",
        "tampered": bool(issues), "capability": capability.as_dict(),
        "reason": reason, "issues": issues, "source_map_validation": validation_payload,
        "traceable": structurally_valid, "execution_origin_verified": executed,
        "identities": dict(recorded), "receipt_id": receipt_id,
    }


def bind_current_definition_correspondence_owners(
    source_text: str,
    *,
    request_id: str,
    declared_populations: Mapping[str, Sequence[str]] | None = None,
    scope_correspondence: Mapping[str, Any] | None = None,
    correspondence_requests: Mapping[str, Any] | None = None,
    applicability: Mapping[str, Any] | None = None,
    contextual_review: Mapping[str, Any] | None = None,
    supplied_receipt: Mapping[str, Any] | None = None,
    training_metrics: Any = None,
    graph_join: Any = None,
) -> Dict[str, Any]:
    """Bind current definition and correspondence owners to one exact legal source.

    Receipts count only when the pinned owner regenerates them from the
    forwarded populations. A caller-supplied receipt JSON, a training metric,
    an incomplete graph join, or an unbound definition does not authorize law
    or proof. Regenerated owner reports remain non-authority.
    """

    populations = dict(declared_populations or {})
    limitations = [
        "A regenerated owner receipt is not governing law.",
        "A regenerated owner receipt is not executed proof.",
        "Incomplete graph joins do not authorize law or proof.",
        "Model training metrics do not authorize law or proof.",
        "Unbound definitions do not authorize law or proof.",
        "User-supplied receipt JSON is not a current owner receipt.",
    ]
    record: Dict[str, Any] = {
        "schema": DEFINITION_CORRESPONDENCE_SCHEMA,
        "operation": "bind_current_definition_correspondence_owners",
        "request_id": str(request_id or ""),
        "status": "failed",
        "reason": "",
        "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest() if isinstance(source_text, str) else "",
        "owners": {},
        "authorizes_law": False,
        "authorizes_proof": False,
        "executed_proof": False,
        "governing_legal_authority": False,
        "proof": False,
        "supplied_receipt_ignored": supplied_receipt is not None,
        "training_metrics_authorize_law": False,
        "training_metrics_authorize_proof": False,
        "training_metrics_present": training_metrics is not None,
        "graph_join_authorizes_law": False,
        "graph_join_authorizes_proof": False,
        "graph_join_present": graph_join is not None,
        "incomplete_graph_join": False,
        "definition_unbound": True,
        "limitations": limitations,
    }
    if not isinstance(source_text, str) or not source_text.strip():
        record["reason"] = "legal_source_required"
        return record
    if not isinstance(request_id, str) or not request_id.strip():
        record["reason"] = "request_id_required"
        return record
    normalized: Dict[str, List[str]] = {}
    for family in _REQUIRED_CORRESPONDENCE_FAMILIES:
        required = populations.get(family)
        if not isinstance(required, (list, tuple)) or not required or any(
            not isinstance(item, str) or not item.strip() for item in required
        ):
            record["reason"] = "incomplete_declared_population"
            record["owners"][family] = _failed_family("", "incomplete_declared_population")
            return record
        normalized[family] = [str(item) for item in required]
    if graph_join is not None:
        covered: set[str] = set()
        if isinstance(graph_join, Mapping) and isinstance(graph_join.get("population_ids"), list):
            covered = {item for item in graph_join["population_ids"] if isinstance(item, str)}
        needed = {item for ids in normalized.values() for item in ids}
        record["incomplete_graph_join"] = graph_join.get("complete") is not True if isinstance(graph_join, Mapping) else True
        if not needed <= covered or record["incomplete_graph_join"]:
            record["incomplete_graph_join"] = True
    bundles = {
        "source_correspondence": scope_correspondence,
        "definition_applicability": applicability,
        "contextual_review": contextual_review,
    }
    if any(not isinstance(bundle, Mapping) or not bundle for bundle in bundles.values()):
        record["status"] = "incomplete_graph_join" if record["incomplete_graph_join"] and not any(bundles.values()) else "incomplete"
        record["reason"] = "owner_populations_required" if any(bundles.values()) else (
            "incomplete_graph_join" if record["incomplete_graph_join"] else "owner_populations_required"
        )
        if training_metrics is not None and not any(isinstance(bundle, Mapping) and bundle for bundle in bundles.values()):
            record["status"] = "rejected"
            record["reason"] = "training_metrics_are_not_authority"
        if supplied_receipt is not None and not any(isinstance(bundle, Mapping) and bundle for bundle in bundles.values()):
            record["status"] = "rejected"
            record["reason"] = "supplied_receipt_ignored"
        return record
    try:
        record["owners"]["source_correspondence"] = _replay_scope(
            scope_correspondence, source_text, normalized["source_correspondence"],
        )
        record["owners"]["definition_applicability"] = _replay_applicability(
            applicability, source_text, normalized["definition_applicability"],
        )
        record["owners"]["contextual_review"] = _replay_contextual(
            contextual_review, source_text, normalized["contextual_review"],
            verified_endpoint_bases=record["owners"]["definition_applicability"].pop("verified_contextual_endpoint_bases", {}),
        )
        if isinstance(correspondence_requests, Mapping) and correspondence_requests:
            requests_population = populations.get("source_correspondence_requests") or normalized["source_correspondence"]
            record["owners"]["source_correspondence_requests"] = _replay_correspondence_requests(
                correspondence_requests,
                source_text,
                [str(item) for item in requests_population],
            )
    except Exception as exc:
        record["status"] = "unavailable"
        record["reason"] = str(exc) or type(exc).__name__
        return record
    families = [record["owners"][name] for name in _REQUIRED_CORRESPONDENCE_FAMILIES]
    requests_family = record["owners"].get("source_correspondence_requests")
    if requests_family is not None and requests_family.get("genuine_current_owner_receipt") is not True:
        record["status"] = "rejected"
        record["reason"] = str(requests_family.get("reason") or "correspondence_requests_rejected")
        record["definition_unbound"] = True
        return record
    if any(family.get("reason") == "unbound_definition" for family in families):
        record["status"] = "unbound_definition"
        record["reason"] = "unbound_definition"
        record["definition_unbound"] = True
        return record
    record["definition_unbound"] = any(family.get("definition_unbound") is True for family in families)
    if all(family.get("genuine_current_owner_receipt") is True for family in families) and not record["definition_unbound"]:
        record["status"] = "bound"
        record["reason"] = ""
    elif any(family.get("reason") == "source_unbound" for family in families):
        record["status"] = "source_unbound"
        record["reason"] = "source_unbound"
    elif any(family.get("reason") == "incomplete_declared_population" for family in families):
        record["status"] = "incomplete_declared_population"
        record["reason"] = "incomplete_declared_population"
    else:
        record["status"] = "rejected"
        record["reason"] = next((str(family.get("reason") or "") for family in families if family.get("reason")), "owner_rejected")
    if record["incomplete_graph_join"]:
        record["graph_join_authorizes_law"] = False
        record["graph_join_authorizes_proof"] = False
    return record


def connect_definition_handoff_proof(
    requirement: Mapping[str, Any],
    handoff: Mapping[str, Any] | None = None,
    *,
    provider: Any = None,
) -> Dict[str, Any]:
    """Bind current definition-handoff identities to obligation and route owners.

    A solver selector, generated Lean packet, or review packet is recorded and
    is not a proved result. The requirement proof field changes only when an
    issued evaluation is verified and satisfied against the same identities.
    Factual assertion stays separate from legal sufficiency.
    """

    requirement_map = dict(requirement or {})
    bound = dict(handoff or {})
    retained = bound.get("retained") if isinstance(bound.get("retained"), Mapping) else {}
    assumptions = list(retained.get("assumptions") or requirement_map.get("assumptions") or [])
    requirement_id = str(bound.get("requirement_id") or requirement_map.get("requirement_id") or "")
    source_text = requirement_map.get("admitted_legal_text")
    if not isinstance(source_text, str):
        source_text = str(bound.get("admitted_legal_text") or "")
    treatment = bound.get("adverse_treatment", requirement_map.get("adverse_treatment"))
    obligations = generate_bound_legal_ir_proof_obligations(
        None,
        claim_id=str(requirement_map.get("claim_id") or ""),
        element_id=str(requirement_map.get("element_id") or requirement_id),
        assumptions=assumptions,
        asserted_facts=requirement_map.get("asserted_facts") if isinstance(requirement_map.get("asserted_facts"), list) else [],
        selected_legal_rules=requirement_map.get("selected_legal_rules") if isinstance(requirement_map.get("selected_legal_rules"), list) else [],
        source_text=source_text,
        requirement_id=requirement_id,
        definition_binding=bound,
        adverse_treatment=treatment,
        use_cache=False,
    )
    versions = obligations.get("versions") if isinstance(obligations.get("versions"), Mapping) else {}
    inventory = obligations.get("premise_inventory") if isinstance(obligations.get("premise_inventory"), Mapping) else {}
    identity = proof_cache_identity(
        claim_id=str(requirement_map.get("claim_id") or ""),
        element_id=str(requirement_map.get("element_id") or requirement_id),
        factual_revisions=versions.get("fact_revisions") or [],
        legal_source={
            "source_id": str(requirement_map.get("source_id") or ""),
            "source_version": str(versions.get("legal_context_version") or ""),
            "requirement_id": str(versions.get("requirement_id") or ""),
            "definition_identity": str(versions.get("definition_identity") or ""),
            "assumption_identity": str(versions.get("assumption_identity") or ""),
            "adverse_treatment_identity": str(versions.get("adverse_treatment_identity") or ""),
            "source_identity": str(versions.get("source_identity") or ""),
            "premise_inventory": inventory,
        },
        compiler={"execution_identity": str(versions.get("execution_identity") or "")},
    )
    packet_outcome = _nonproof_packet_outcome(bound)

    def _route():
        if provider is not None:
            return provider()
        return route_bound_legal_ir_proof(
            premise_inventory=inventory,
            goal_statement=source_text,
            execution_identity=str(versions.get("execution_identity") or ""),
            expected_execution_identity=str(versions.get("execution_identity") or ""),
            requirement_id=str(versions.get("requirement_id") or ""),
            expected_requirement_id=str(versions.get("requirement_id") or ""),
            definition_identity=str(versions.get("definition_identity") or ""),
            expected_definition_identity=str(versions.get("definition_identity") or ""),
            assumption_identity=str(versions.get("assumption_identity") or ""),
            expected_assumption_identity=str(versions.get("assumption_identity") or ""),
            adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
            expected_adverse_treatment_identity=str(versions.get("adverse_treatment_identity") or ""),
            source_identity=str(versions.get("source_identity") or ""),
            expected_source_identity=str(versions.get("source_identity") or ""),
            premise_version=str(inventory.get("digest") or ""),
            expected_premise_version=str(inventory.get("digest") or ""),
        )

    evaluation = replay_satisfied_element_proof(identity, provider=_route)
    routed = evaluation.get("result") if isinstance(evaluation.get("result"), Mapping) else {}
    outcome = str(routed.get("outcome") or evaluation.get("status") or "unknown")
    if packet_outcome:
        outcome = packet_outcome
    verified = verify_element_proof_evaluation(evaluation)
    proof_supported = bool(verified.get("verified") and verified.get("satisfied") and outcome == "proved")
    original_proof = requirement_map.get("proof")
    return {
        "schema": "definition-handoff-proof-binding/v1",
        "requirement_id": requirement_id,
        "admitted_legal_text": source_text,
        "admitted_legal_text_changed": False,
        "proof": original_proof if proof_supported else original_proof,
        "proof_field_supported": proof_supported,
        "proof_satisfied": proof_supported,
        "proof_changed": False,
        "factual_assertion": {
            "asserted": bool(requirement_map.get("asserted_facts")),
            "satisfies_element": False,
        },
        "legal_sufficiency": {
            "outcome": outcome,
            "satisfied": proof_supported,
        },
        "outcome": outcome,
        "outcome_distinctions": list(PROOF_ROUTING_OUTCOMES),
        "solver_is_proof": False,
        "generated_lean_is_proof": False,
        "review_packet_is_proof": False,
        "legal_ir_proof_obligations": obligations,
        "legal_ir_proof_routing": dict(routed) if routed else {"outcome": outcome, "substantive_trust_satisfied": False},
        "proof_cache_identity": identity.get("cache_identity"),
        "evaluation": evaluation,
        "versions": dict(versions),
    }


from . import logic as _logic_owner
from .logic import route_bound_legal_ir_proof


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
    "_bridge_canonical_source_map",
    "audit_canonical_formalization_payload",
    "bind_current_definition_correspondence_owners",
    "extract_source_bound_rule_candidates",
    "connect_definition_handoff_proof",
)

for _name in _MOVED:
    _fn = _bind_to_owner_globals(globals()[_name])
    globals()[_name] = _fn
    setattr(_logic_owner, _name, _fn)
