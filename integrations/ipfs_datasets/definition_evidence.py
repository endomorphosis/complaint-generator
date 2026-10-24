"""First-party adapter for current source-sampling context and definition evidence.

The sampling-context and contextual definition binding/review owners keep the
replay, population, and correspondence rules. This module only forwards whole
source, context, attachment, and response populations with the caller's
explicit declaration and request hashes. A prepared or replayed context does
not grant applicability, truth, training, graph, or proof authority, and it
does not collapse candidate, source-review, and meaning-review states.
"""

from __future__ import annotations

from typing import Any

from .loader import import_module_optional


SCHEMA = "complaint-mediator-source-sampling-definition-evidence/v1"

_CONTEXT_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_review_context"
_BINDING_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_binding_v2"
_REVIEW_MODULE_NAME = "ipfs_datasets_py.logic.autoformal.legal_source_sampling_context_definition_review_v2"

_context_module, _context_error = import_module_optional(_CONTEXT_MODULE_NAME)
_binding_module, _binding_error = import_module_optional(_BINDING_MODULE_NAME)
_review_module, _review_error = import_module_optional(_REVIEW_MODULE_NAME)

_CONTEXT_SCHEMA = "legal-source-sampling-review-context/v1"
_RESPONSE_SCHEMA = "legal-source-sampling-context-declaration/v1"
_POPULATION_SCHEMA = "legal-source-sampling-context-population/v1"
_BINDING_SCHEMA = "legal-source-sampling-context-definition-binding/v2"
_REVIEW_SCHEMA = "legal-source-sampling-context-definition-review-correspondence/v1"
_ACCEPTED_SCHEMAS = {
    _CONTEXT_SCHEMA,
    _RESPONSE_SCHEMA,
    _POPULATION_SCHEMA,
    _BINDING_SCHEMA,
    _REVIEW_SCHEMA,
}

_DENIED_AUTHORITY = {
    "applicability": False,
    "truth": False,
    "training": False,
    "graph": False,
    "proof": False,
}


def _diagnostic(error: Any) -> dict[str, str] | None:
    if error is None:
        return None
    as_dict = getattr(error, "as_dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return {"error_type": type(error).__name__, "message": str(error)}


def _subject_key(bundle_sha256: Any, subject: Any) -> tuple[Any, ...] | None:
    if not isinstance(subject, dict):
        return None
    return (
        bundle_sha256,
        subject.get("kind"),
        subject.get("index"),
        subject.get("sha256"),
    )


def _nominations(attachments: Any) -> list[dict[str, Any]]:
    if not isinstance(attachments, list):
        return []
    rows = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        nomination = item.get("nomination", item)
        if isinstance(nomination, dict) and "supporting_bundle_sha256" in nomination:
            rows.append(nomination)
    return rows


def _unreviewed_supporting_subjects(owner_result: dict[str, Any], attachments: Any) -> list[dict[str, Any]]:
    """Supporting endpoints that still have no recorded declaration."""

    supporting = []
    seen = set()
    for nomination in _nominations(attachments):
        key = _subject_key(
            nomination.get("supporting_bundle_sha256"),
            nomination.get("supporting_subject_ref"),
        )
        if key is None or key in seen:
            continue
        seen.add(key)
        supporting.append({
            "bundle_sha256": nomination.get("supporting_bundle_sha256"),
            "subject_ref": nomination.get("supporting_subject_ref"),
            "role": nomination.get("role"),
        })
    if not supporting:
        return []
    declared: set[tuple[Any, ...]] = set()
    subjects = owner_result.get("subjects")
    if not isinstance(subjects, list):
        population = owner_result.get("contextual_population")
        if isinstance(population, dict):
            subjects = population.get("subjects")
    if isinstance(subjects, list):
        for row in subjects:
            if isinstance(row, dict) and row.get("response_refs"):
                key = _subject_key(row.get("bundle_sha256"), row.get("subject_ref"))
                if key is not None:
                    declared.add(key)
    return [
        row for row in supporting
        if _subject_key(row["bundle_sha256"], row["subject_ref"]) not in declared
    ]


def _states(owner_result: dict[str, Any]) -> dict[str, Any]:
    """Keep candidate, source-review, and meaning-review observations distinct."""

    schema = owner_result.get("schema")
    if schema == _CONTEXT_SCHEMA:
        return {
            "candidate": "not_a_definition_candidate",
            "source_review": "unreviewed",
            "meaning_review": "unreviewed",
            "context_status": owner_result.get("status"),
        }
    if schema == _RESPONSE_SCHEMA:
        declaration = owner_result.get("declaration")
        source_dispositions = []
        meaning_dispositions = []
        if isinstance(declaration, dict):
            for row in declaration.get("source_answers") or []:
                if isinstance(row, dict):
                    source_dispositions.append(row.get("disposition"))
            for row in declaration.get("meaning_proposals") or []:
                if isinstance(row, dict):
                    meaning_dispositions.append(row.get("disposition"))
        return {
            "candidate": "not_a_definition_candidate",
            "source_review": owner_result.get("status"),
            "meaning_review": "unreviewed",
            "source_dispositions": source_dispositions,
            "meaning_dispositions": meaning_dispositions,
        }
    if schema == _POPULATION_SCHEMA:
        return {
            "candidate": "not_a_definition_candidate",
            "source_review": "unreviewed" if owner_result.get("review_completed") is False else owner_result.get("status"),
            "meaning_review": "unreviewed" if owner_result.get("adjudication_performed") is False else owner_result.get("status"),
            "population_counts": owner_result.get("counts"),
            "review_completed": owner_result.get("review_completed"),
            "adjudication_performed": owner_result.get("adjudication_performed"),
        }
    if schema == _BINDING_SCHEMA:
        base = owner_result.get("base_binding")
        contextual = owner_result.get("contextual_binding")
        binding = base.get("binding") if isinstance(base, dict) else None
        return {
            "candidate": binding.get("status") if isinstance(binding, dict) else None,
            "candidate_interpretation": binding.get("interpretation_status") if isinstance(binding, dict) else None,
            "source_review": contextual.get("status") if isinstance(contextual, dict) else None,
            "meaning_review": contextual.get("interpretation_status") if isinstance(contextual, dict) else None,
        }
    if schema == _REVIEW_SCHEMA:
        definition = owner_result.get("definition_correspondence")
        contextual = owner_result.get("contextual_correspondence")
        definition = definition if isinstance(definition, dict) else {}
        contextual = contextual if isinstance(contextual, dict) else {}
        return {
            "candidate": definition.get("view"),
            "candidate_status": definition.get("status"),
            "source_review": contextual.get("source_declaration_status"),
            "meaning_review": definition.get("source_declaration_status"),
            "meaning_assessment_created": definition.get("assessment_created"),
            "related_declarations_close_definition_review": contextual.get(
                "related_declarations_close_definition_review"
            ),
        }
    return {
        "candidate": None,
        "source_review": None,
        "meaning_review": None,
    }


def _population(owner_result: dict[str, Any], attachments: Any) -> dict[str, Any]:
    counts = owner_result.get("counts") if isinstance(owner_result.get("counts"), dict) else {}
    contextual = owner_result.get("contextual_population")
    if isinstance(contextual, dict) and isinstance(contextual.get("counts"), dict):
        counts = contextual["counts"]
    supporting = _unreviewed_supporting_subjects(owner_result, attachments)
    packet_counts = owner_result.get("context_counts")
    if not isinstance(packet_counts, dict):
        binding = owner_result.get("contextual_binding")
        if isinstance(binding, dict) and isinstance(binding.get("context_counts"), dict):
            packet_counts = binding["context_counts"]
        elif isinstance(owner_result.get("contextual_correspondence"), dict):
            packet_counts = owner_result["contextual_correspondence"].get("context_counts")
    if not isinstance(packet_counts, dict):
        packet_counts = counts if "sources" in counts else {}
    return {
        "source_count": packet_counts.get("sources", counts.get("sources")),
        "attachment_count": packet_counts.get("attachments", owner_result.get("attachment_count")),
        "subject_count": packet_counts.get("subjects", owner_result.get("subject_count")),
        "response_count": owner_result.get("response_count"),
        "population_counts": counts or None,
        "unreviewed_supporting_subjects": supporting,
        "unreviewed_supporting_subject_count": len(supporting),
    }


def _hashes(**pins: Any) -> dict[str, Any]:
    bound = {}
    for key, value in pins.items():
        if value is None:
            continue
        bound[key] = list(value) if isinstance(value, (list, tuple)) else value
    return bound


def _envelope(
    *,
    status: str,
    operation: str,
    owner: str,
    owner_function: str,
    result: dict[str, Any] | None,
    reason: str | None,
    error_type: str | None,
    hashes: dict[str, Any],
    attachments: Any,
    dependency: dict[str, str] | None = None,
) -> dict[str, Any]:
    owner_authority = None
    training_mask = 0
    evaluation_gold_mask = 0
    states = {"candidate": None, "source_review": None, "meaning_review": None}
    population = {
        "source_count": None,
        "attachment_count": None,
        "subject_count": None,
        "response_count": None,
        "population_counts": None,
        "unreviewed_supporting_subjects": [],
        "unreviewed_supporting_subject_count": 0,
    }
    if isinstance(result, dict):
        authority = result.get("authority")
        if isinstance(authority, dict):
            owner_authority = dict(authority)
        else:
            contextual = result.get("contextual_binding")
            if isinstance(contextual, dict) and isinstance(contextual.get("authority"), dict):
                owner_authority = dict(contextual["authority"])
            correspondence = result.get("contextual_correspondence")
            if isinstance(correspondence, dict) and isinstance(correspondence.get("authority"), dict):
                owner_authority = dict(correspondence["authority"])
        if isinstance(result.get("training_mask"), int):
            training_mask = result["training_mask"]
        if isinstance(result.get("evaluation_gold_mask"), int):
            evaluation_gold_mask = result["evaluation_gold_mask"]
        states = _states(result)
        population = _population(result, attachments)
        if result.get("schema") == _REVIEW_SCHEMA:
            contextual = result.get("contextual_correspondence")
            if isinstance(contextual, dict):
                if isinstance(contextual.get("training_mask"), int):
                    training_mask = contextual["training_mask"]
                if isinstance(contextual.get("evaluation_gold_mask"), int):
                    evaluation_gold_mask = contextual["evaluation_gold_mask"]
    return {
        "schema": SCHEMA,
        "status": status,
        "operation": operation,
        "owner": owner,
        "owner_function": owner_function,
        "reason": reason,
        "error_type": error_type,
        "dependency": dependency,
        "result": result,
        "states": states,
        "population": population,
        "bound_hashes": hashes,
        "owner_authority": owner_authority,
        "authority_granted": dict(_DENIED_AUTHORITY),
        "applicability_granted": False,
        "truth_granted": False,
        "training_authority_granted": False,
        "graph_authority_granted": False,
        "proof_authority_granted": False,
        "training_mask": training_mask,
        "evaluation_gold_mask": evaluation_gold_mask,
        "legal_review_completed": False,
        "fabricated": False,
    }


def _invoke(
    module: Any,
    error: Any,
    module_name: str,
    function_name: str,
    operation: str,
    /,
    *args: Any,
    attachments: Any = None,
    hashes: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    bound = hashes or {}
    if module is None or not callable(getattr(module, function_name, None)):
        diagnostic = _diagnostic(error)
        return _envelope(
            status="unavailable",
            operation=operation,
            owner=module_name,
            owner_function=function_name,
            result=None,
            reason="owner_unavailable" if module is None else "owner_function_unavailable",
            error_type=None if diagnostic is None else diagnostic.get("error_type"),
            hashes=bound,
            attachments=attachments,
            dependency=diagnostic,
        )
    try:
        result = getattr(module, function_name)(*args, **kwargs)
    except Exception as exc:
        return _envelope(
            status="failed",
            operation=operation,
            owner=module_name,
            owner_function=function_name,
            result=None,
            reason=str(exc) or type(exc).__name__,
            error_type=type(exc).__name__,
            hashes=bound,
            attachments=attachments,
        )
    if not isinstance(result, dict) or result.get("schema") not in _ACCEPTED_SCHEMAS:
        return _envelope(
            status="failed",
            operation=operation,
            owner=module_name,
            owner_function=function_name,
            result=result if isinstance(result, dict) else None,
            reason="unexpected_owner_schema",
            error_type="UnexpectedOwnerSchema",
            hashes=bound,
            attachments=attachments,
        )
    return _envelope(
        status="replayed",
        operation=operation,
        owner=module_name,
        owner_function=function_name,
        result=result,
        reason=None,
        error_type=None,
        hashes=bound,
        attachments=attachments,
    )


def prepare_sampling_review_context(
    sources: Any,
    attachments: Any,
    *,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Replay whole sources and the exact attachment population."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "prepare",
        "prepare_sampling_review_context",
        sources,
        attachments,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(expected_attachments_sha256=expected_attachments_sha256),
    )


def validate_sampling_review_context(
    packet: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_context_sha256: str,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Replay the pinned context against the whole source and attachment populations."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "validate",
        "validate_sampling_review_context",
        packet,
        sources,
        attachments,
        expected_context_sha256=expected_context_sha256,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_context_sha256=expected_context_sha256,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def record_sampling_review_context_response(
    packet: Any,
    declaration: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_context_sha256: str,
    expected_declaration_sha256: str,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Record one explicit declaration hash against the whole context population."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "record_response",
        "record_sampling_review_context_response",
        packet,
        declaration,
        sources,
        attachments,
        expected_context_sha256=expected_context_sha256,
        expected_declaration_sha256=expected_declaration_sha256,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_context_sha256=expected_context_sha256,
            expected_declaration_sha256=expected_declaration_sha256,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def validate_sampling_review_context_response(
    response: Any,
    packet: Any,
    declaration: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_response_sha256: str,
    expected_context_sha256: str,
    expected_declaration_sha256: str,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Replay one recorded declaration without promoting source or meaning review."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "validate_response",
        "validate_sampling_review_context_response",
        response,
        packet,
        declaration,
        sources,
        attachments,
        expected_response_sha256=expected_response_sha256,
        expected_context_sha256=expected_context_sha256,
        expected_declaration_sha256=expected_declaration_sha256,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_response_sha256=expected_response_sha256,
            expected_context_sha256=expected_context_sha256,
            expected_declaration_sha256=expected_declaration_sha256,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def summarize_sampling_review_context(
    packet: Any,
    responses: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_context_sha256: str,
    expected_response_sha256s: Any,
    expected_attachments_sha256: str,
    limits: Any = None,
) -> dict[str, Any]:
    """Retain every subject, including supporting sources with no declaration."""

    return _invoke(
        _context_module,
        _context_error,
        _CONTEXT_MODULE_NAME,
        "summarize",
        "summarize_sampling_review_context",
        packet,
        responses,
        sources,
        attachments,
        expected_context_sha256=expected_context_sha256,
        expected_response_sha256s=expected_response_sha256s,
        expected_attachments_sha256=expected_attachments_sha256,
        limits=limits,
        attachments=attachments,
        hashes=_hashes(
            expected_context_sha256=expected_context_sha256,
            expected_response_sha256s=expected_response_sha256s,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def prepare_contextual_definition_binding(
    request_raw: Any,
    context: Any,
    responses: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_request_sha256: str,
    expected_definition_bundle_sha256: str,
    expected_context_sha256: str,
    expected_response_sha256s: Any,
    expected_attachments_sha256: str,
) -> dict[str, Any]:
    """Bind the explicit request hash to the whole context population."""

    return _invoke(
        _binding_module,
        _binding_error,
        _BINDING_MODULE_NAME,
        "prepare",
        "prepare_contextual_definition_binding",
        request_raw,
        context,
        responses,
        sources,
        attachments,
        expected_request_sha256=expected_request_sha256,
        expected_definition_bundle_sha256=expected_definition_bundle_sha256,
        expected_context_sha256=expected_context_sha256,
        expected_response_sha256s=expected_response_sha256s,
        expected_attachments_sha256=expected_attachments_sha256,
        attachments=attachments,
        hashes=_hashes(
            expected_request_sha256=expected_request_sha256,
            expected_definition_bundle_sha256=expected_definition_bundle_sha256,
            expected_context_sha256=expected_context_sha256,
            expected_response_sha256s=expected_response_sha256s,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def validate_contextual_definition_binding(
    result: Any,
    request_raw: Any,
    context: Any,
    responses: Any,
    sources: Any,
    attachments: Any,
    *,
    expected_binding_sha256: str,
    expected_request_sha256: str,
    expected_definition_bundle_sha256: str,
    expected_context_sha256: str,
    expected_response_sha256s: Any,
    expected_attachments_sha256: str,
) -> dict[str, Any]:
    """Regenerate the contextual binding from the same whole populations."""

    return _invoke(
        _binding_module,
        _binding_error,
        _BINDING_MODULE_NAME,
        "validate",
        "validate_contextual_definition_binding",
        result,
        request_raw,
        context,
        responses,
        sources,
        attachments,
        expected_binding_sha256=expected_binding_sha256,
        expected_request_sha256=expected_request_sha256,
        expected_definition_bundle_sha256=expected_definition_bundle_sha256,
        expected_context_sha256=expected_context_sha256,
        expected_response_sha256s=expected_response_sha256s,
        expected_attachments_sha256=expected_attachments_sha256,
        attachments=attachments,
        hashes=_hashes(
            expected_binding_sha256=expected_binding_sha256,
            expected_request_sha256=expected_request_sha256,
            expected_definition_bundle_sha256=expected_definition_bundle_sha256,
            expected_context_sha256=expected_context_sha256,
            expected_response_sha256s=expected_response_sha256s,
            expected_attachments_sha256=expected_attachments_sha256,
        ),
    )


def prepare_contextual_definition_review(
    binding_result: Any,
    review_subject: Any,
    *,
    expected_binding_sha256: str,
    expected_subject_sha256: str,
    contextual_replay_inputs: Any,
    candidate_inputs: Any,
    expected_candidate_pin: Any,
    context_inputs: Any,
    expected_context_population: Any,
    dependency_manifest: Any,
    expected_manifest_sha256: str,
    required_dependency_ids: Any,
) -> dict[str, Any]:
    """Replay contextual correspondence without covering the meaning subject."""

    attachments = None
    responses = None
    if isinstance(contextual_replay_inputs, dict):
        attachments = contextual_replay_inputs.get("attachments")
        responses = contextual_replay_inputs.get("responses")
    return _invoke(
        _review_module,
        _review_error,
        _REVIEW_MODULE_NAME,
        "prepare",
        "prepare_contextual_definition_review",
        binding_result,
        review_subject,
        expected_binding_sha256=expected_binding_sha256,
        expected_subject_sha256=expected_subject_sha256,
        contextual_replay_inputs=contextual_replay_inputs,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=expected_candidate_pin,
        context_inputs=context_inputs,
        expected_context_population=expected_context_population,
        dependency_manifest=dependency_manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        required_dependency_ids=required_dependency_ids,
        attachments=attachments,
        hashes=_hashes(
            expected_binding_sha256=expected_binding_sha256,
            expected_subject_sha256=expected_subject_sha256,
            expected_request_sha256=(
                contextual_replay_inputs.get("expected_request_sha256")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_context_sha256=(
                contextual_replay_inputs.get("expected_context_sha256")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_response_sha256s=(
                contextual_replay_inputs.get("expected_response_sha256s")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_attachments_sha256=(
                contextual_replay_inputs.get("expected_attachments_sha256")
                if isinstance(contextual_replay_inputs, dict) else None
            ),
            expected_manifest_sha256=expected_manifest_sha256,
        ),
    )


def validate_contextual_definition_review(
    correspondence: Any,
    binding_result: Any,
    review_subject: Any,
    *,
    expected_correspondence_sha256: str,
    expected_binding_sha256: str,
    expected_subject_sha256: str,
    contextual_replay_inputs: Any,
    candidate_inputs: Any,
    expected_candidate_pin: Any,
    context_inputs: Any,
    expected_context_population: Any,
    dependency_manifest: Any,
    expected_manifest_sha256: str,
    required_dependency_ids: Any,
) -> dict[str, Any]:
    """Regenerate the contextual review envelope under its independent pin."""

    attachments = None
    if isinstance(contextual_replay_inputs, dict):
        attachments = contextual_replay_inputs.get("attachments")
    return _invoke(
        _review_module,
        _review_error,
        _REVIEW_MODULE_NAME,
        "validate",
        "validate_contextual_definition_review",
        correspondence,
        binding_result,
        review_subject,
        expected_correspondence_sha256=expected_correspondence_sha256,
        expected_binding_sha256=expected_binding_sha256,
        expected_subject_sha256=expected_subject_sha256,
        contextual_replay_inputs=contextual_replay_inputs,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=expected_candidate_pin,
        context_inputs=context_inputs,
        expected_context_population=expected_context_population,
        dependency_manifest=dependency_manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        required_dependency_ids=required_dependency_ids,
        attachments=attachments,
        hashes=_hashes(
            expected_correspondence_sha256=expected_correspondence_sha256,
            expected_binding_sha256=expected_binding_sha256,
            expected_subject_sha256=expected_subject_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        ),
    )
