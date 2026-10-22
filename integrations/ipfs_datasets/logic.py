from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
from enum import Enum
import hashlib
import inspect
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from lib.formal_logic.capabilities import (
    CanonicalCompilerCapability,
    CanonicalCompilerSupport,
    FormalLogicCapability,
    FormalLogicCapabilityError,
    FormalLogicDegradedError,
    FormalLogicOperation,
    FormalLogicUnavailableError,
    LogicCapabilityState,
    LogicCapabilityStatus,
    classify_canonical_compiler_capability,
)
from lib.formal_logic.frames import FrameKnowledgeBase

from .loader import import_module_optional
from .types import with_adapter_metadata


_logic_module, _logic_error = import_module_optional("ipfs_datasets_py.logic")
_fol_module, _fol_error = import_module_optional("ipfs_datasets_py.logic.fol")
_deontic_module, _deontic_error = import_module_optional("ipfs_datasets_py.logic.deontic")
_tdfol_module, _tdfol_error = import_module_optional("ipfs_datasets_py.logic.TDFOL")
_integration_module, _integration_error = import_module_optional("ipfs_datasets_py.logic.integration")
_external_provers_module, _external_provers_error = import_module_optional(
    "ipfs_datasets_py.logic.external_provers"
)
_z3_module, _z3_error = import_module_optional(
    "ipfs_datasets_py.logic.external_provers.smt.z3_prover_bridge"
)
# If the ipfs_datasets_py z3 bridge is absent, try the standalone z3-solver package.
_local_z3_module: Any = None
if _z3_module is None:
    _local_z3_module, _ = import_module_optional("z3")
_reasoner_module, _reasoner_error = import_module_optional(
    "ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
)
if _reasoner_module is None:
    _reasoner_module, _reasoner_error = import_module_optional(
        "ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
    )

LOGIC_AVAILABLE = any(
    value is not None
    for value in (
        _logic_module,
        _fol_module,
        _deontic_module,
        _tdfol_module,
        _integration_module,
        _external_provers_module,
    )
)
LOGIC_ERROR = (
    _logic_error
    or _fol_error
    or _deontic_error
    or _tdfol_error
    or _integration_error
    or _external_provers_error
    or _z3_error
)
Z3_AVAILABLE = _z3_module is not None or _local_z3_module is not None
REASONER_BRIDGE_AVAILABLE = _reasoner_module is not None
REASONER_BRIDGE_ERROR = _reasoner_error
REASONER_BRIDGE_PATH = getattr(_reasoner_module, "__name__", "") if _reasoner_module is not None else ""
LOCAL_FORMAL_LOGIC_AVAILABLE = True
LOCAL_FORMAL_LOGIC_PATH = "lib.formal_logic"
LOGIC_CAPABILITY_SCHEMA_VERSION = "formal-logic-capabilities/v1"

_canonical_pipeline_module, _canonical_pipeline_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_canonical_pipeline"
)
_canonical_contracts_module, _canonical_contracts_error = import_module_optional(
    "ipfs_datasets_py.logic.legal_ir.canonical_contracts"
)
_canonical_compiler_module, _canonical_compiler_error = import_module_optional(
    "ipfs_datasets_py.logic.legal_ir.canonical_compiler"
)
_canonical_source_map_module, _canonical_source_map_error = import_module_optional(
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_source_maps"
)
_CANONICAL_FORMALIZATION_RECEIPTS: Dict[str, Dict[str, Any]] = {}
_CANONICAL_FORMALIZATION_CACHE: Dict[str, str] = {}
_CANONICAL_SUPPORTED_EXECUTION: Dict[str, Any] | None = None

_DEGRADED_OPERATION_REASONS = {
    FormalLogicOperation.TEXT_TO_FOL: (
        "The FOL provider imports, but this adapter exposes only a structural "
        "conversion contract; authoritative text-to-FOL conversion is unavailable."
    ),
    FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC: (
        "The deontic provider imports, but this adapter exposes only a structural "
        "conversion contract; authoritative legal-rule translation is unavailable."
    ),
    FormalLogicOperation.PROVE_CLAIM_ELEMENTS: (
        "TDFOL is available for formula construction, but claim-element proof "
        "execution is not connected to a complete prover contract."
    ),
    FormalLogicOperation.CHECK_CONTRADICTIONS: (
        "TDFOL is available for formula construction, but contradiction checking "
        "is limited to structural signal extraction."
    ),
}


def _provider_diagnostic(error: Any, *, fallback: str) -> str:
    diagnostic = str(error or "").strip()
    return diagnostic or fallback


def get_logic_capability(
    operation: FormalLogicOperation | str,
) -> FormalLogicCapability:
    """Return the typed runtime contract for one logic operation.

    Importing the broad provider package is not evidence that every operation
    works.  Each operation is gated by the module it actually needs.  Degraded
    operations may return deterministic structural payloads, while strict
    validation callers can demand a complete implementation before execution.
    """

    normalized_operation = FormalLogicOperation.coerce(operation)
    module: Any = None
    error: Any = None
    module_path = ""

    if normalized_operation is FormalLogicOperation.TEXT_TO_FOL:
        module, error, module_path = _fol_module, _fol_error, "ipfs_datasets_py.logic.fol"
    elif normalized_operation is FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC:
        module, error, module_path = (
            _deontic_module,
            _deontic_error,
            "ipfs_datasets_py.logic.deontic",
        )
    elif normalized_operation in {
        FormalLogicOperation.PROVE_CLAIM_ELEMENTS,
        FormalLogicOperation.CHECK_CONTRADICTIONS,
    }:
        module, error, module_path = (
            _tdfol_module,
            _tdfol_error,
            "ipfs_datasets_py.logic.TDFOL",
        )
    else:
        local_implemented = bool(LOCAL_FORMAL_LOGIC_AVAILABLE)
        reasoner_implemented = bool(REASONER_BRIDGE_AVAILABLE)
        if local_implemented or reasoner_implemented:
            provider = LOCAL_FORMAL_LOGIC_PATH if local_implemented else REASONER_BRIDGE_PATH
            return FormalLogicCapability(
                operation=normalized_operation,
                state=LogicCapabilityState.IMPLEMENTED,
                provider=provider,
                module_path=provider,
                details={
                    "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
                    "local_formal_logic_available": local_implemented,
                    "reasoner_bridge_available": reasoner_implemented,
                    "reasoner_bridge_path": REASONER_BRIDGE_PATH,
                },
            )
        return FormalLogicCapability(
            operation=normalized_operation,
            state=LogicCapabilityState.UNAVAILABLE,
            provider="ipfs_datasets_py",
            module_path=REASONER_BRIDGE_PATH or LOCAL_FORMAL_LOGIC_PATH,
            reason=_provider_diagnostic(
                REASONER_BRIDGE_ERROR,
                fallback="Neither the local formal-logic bridge nor the reasoner bridge is available.",
            ),
            details={"schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION},
        )

    # Keep the aggregate probe as a startup master switch, but retain the
    # operation-specific module and diagnostic in the returned contract.
    if not LOGIC_AVAILABLE:
        module = None
        error = error or LOGIC_ERROR

    if module is None:
        return FormalLogicCapability(
            operation=normalized_operation,
            state=LogicCapabilityState.UNAVAILABLE,
            provider="ipfs_datasets_py",
            module_path=module_path,
            reason=_provider_diagnostic(
                error,
                fallback=f"Required provider module '{module_path}' is unavailable.",
            ),
            details={
                "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
                "local_formal_logic_available": bool(LOCAL_FORMAL_LOGIC_AVAILABLE),
            },
        )

    return FormalLogicCapability(
        operation=normalized_operation,
        state=LogicCapabilityState.DEGRADED,
        provider="ipfs_datasets_py",
        module_path=module_path,
        reason=_DEGRADED_OPERATION_REASONS[normalized_operation],
        details={
            "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
            "local_formal_logic_available": bool(LOCAL_FORMAL_LOGIC_AVAILABLE),
        },
    )


def get_logic_capabilities() -> Dict[FormalLogicOperation, FormalLogicCapability]:
    """Return capability contracts keyed by the typed operation enum."""

    return {operation: get_logic_capability(operation) for operation in FormalLogicOperation}


def get_logic_capability_report() -> Dict[str, Any]:
    """Return a JSON-ready summary of all formal-logic capabilities."""

    capabilities = get_logic_capabilities()
    state_counts = {
        state.value: sum(
            capability.state is state for capability in capabilities.values()
        )
        for state in LogicCapabilityState
    }
    return {
        "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
        "state_counts": state_counts,
        "capabilities": {
            operation.value: capability.as_dict()
            for operation, capability in capabilities.items()
        },
        "unavailable": [
            operation.value
            for operation, capability in capabilities.items()
            if not capability.available
        ],
        "degraded": [
            operation.value
            for operation, capability in capabilities.items()
            if capability.degraded
        ],
        "implemented": [
            operation.value
            for operation, capability in capabilities.items()
            if capability.implemented
        ],
    }


def require_logic_capability(
    operation: FormalLogicOperation | str,
    *,
    allow_degraded: bool = False,
) -> FormalLogicCapability:
    """Gate an operation and raise a typed, predictable capability error."""

    capability = get_logic_capability(operation)
    if allow_degraded:
        return capability.require_available()
    return capability.require_implemented()


def _logic_operation_metadata(capability: FormalLogicCapability) -> Dict[str, Any]:
    return {
        "capability_status": capability.state.value,
        "capability_available": capability.available,
        "capability_degraded": capability.degraded,
        "capability_implemented": capability.implemented,
        "capability": capability.as_dict(),
        "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
        "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
    }


def _selected_logic_path(*candidates: tuple[Any, str], fallback: str = "local") -> str:
    for module, path in candidates:
        if module is not None:
            return path
    return fallback

# Maximum byte length of a Z3 Boolean variable atom name (avoids identifier
# overflow for long formula strings submitted to the local z3-solver fallback).
_Z3_ATOM_NAME_MAX_LENGTH = 60


def _normalize_logic_symbol(value: Any, *, prefix: str) -> str:
    text = str(value or "").strip().lower()
    normalized = ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')
    if not normalized:
        normalized = prefix
    if normalized[0].isdigit():
        normalized = f"{prefix}_{normalized}"
    return normalized


def _normalize_time_symbol(date_value: Any, *, fallback: str = "t_unknown") -> str:
    text = str(date_value or "").strip()
    if not text:
        return fallback
    normalized = ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')
    return f"t_{normalized}" if normalized else fallback


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


def _normalize_claim_reasoning_review(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, Any] = {}
    for claim_type, review in value.items():
        claim_key = str(claim_type or "").strip()
        if not claim_key or not isinstance(review, dict):
            continue
        normalized[claim_key] = deepcopy(review)
    return normalized


def _stable_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_payload_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json_dumps(value).encode("utf-8")).hexdigest()


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


def _normalize_proof_bundles(value: Any) -> Dict[str, Dict[str, Any]]:
    bundles: Dict[str, Dict[str, Any]] = {}
    if isinstance(value, dict):
        for raw_key, raw_bundle in value.items():
            bundle = _normalize_temporal_proof_bundle(raw_bundle)
            if not bundle:
                continue
            key = str(raw_key or "").strip()
            if not key:
                key = str(bundle.get("persistence_key") or bundle.get("proof_bundle_id") or "").strip()
            if key:
                bundles[key] = bundle
    single_bundle = _normalize_temporal_proof_bundle(value)
    if single_bundle:
        key = str(
            single_bundle.get("persistence_key")
            or single_bundle.get("proof_bundle_id")
            or ""
        ).strip()
        if key:
            bundles[key] = single_bundle
    return bundles


def _extract_formula_payload_from_proof_bundles(
    proof_bundles: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    tdfol_formulas: List[str] = []
    dcec_formulas: List[str] = []
    tdfol_formula_certainties: Dict[str, str] = {}
    dcec_formula_certainties: Dict[str, str] = {}
    theorem_export_metadata: Dict[str, Any] = {}
    bundle_digests: List[str] = []

    for bundle_key in sorted(proof_bundles):
        bundle = proof_bundles[bundle_key]
        theorem_exports = bundle.get("theorem_exports") if isinstance(bundle.get("theorem_exports"), dict) else {}
        for formula in theorem_exports.get("tdfol_formulas", []) or []:
            normalized_formula = str(formula).strip()
            if normalized_formula and normalized_formula not in tdfol_formulas:
                tdfol_formulas.append(normalized_formula)
        for formula in theorem_exports.get("dcec_formulas", []) or []:
            normalized_formula = str(formula).strip()
            if normalized_formula and normalized_formula not in dcec_formulas:
                dcec_formulas.append(normalized_formula)
        if isinstance(theorem_exports.get("tdfol_formula_certainties"), dict):
            for formula, certainty in theorem_exports["tdfol_formula_certainties"].items():
                normalized_formula = str(formula).strip()
                if normalized_formula:
                    tdfol_formula_certainties[normalized_formula] = str(certainty or "certain")
        if isinstance(theorem_exports.get("dcec_formula_certainties"), dict):
            for formula, certainty in theorem_exports["dcec_formula_certainties"].items():
                normalized_formula = str(formula).strip()
                if normalized_formula:
                    dcec_formula_certainties[normalized_formula] = str(certainty or "certain")
        metadata = theorem_exports.get("theorem_export_metadata")
        if isinstance(metadata, dict) and not theorem_export_metadata:
            theorem_export_metadata = deepcopy(metadata)
        bundle_digest = str(bundle.get("bundle_digest") or "").strip()
        if bundle_digest and bundle_digest not in bundle_digests:
            bundle_digests.append(bundle_digest)

    if theorem_export_metadata:
        theorem_export_metadata = deepcopy(theorem_export_metadata)
        theorem_export_metadata["proof_bundle_digests"] = bundle_digests
        theorem_export_metadata["proof_execution_source"] = "temporal_proof_bundle"

    return {
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "tdfol_formula_certainties": tdfol_formula_certainties,
        "dcec_formula_certainties": dcec_formula_certainties,
        "theorem_export_metadata": theorem_export_metadata,
        "proof_bundle_digests": bundle_digests,
    }


def _summarize_fact_registry_for_facts(support_facts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    facts = [fact for fact in support_facts or [] if isinstance(fact, dict)]
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    parse_source_counts: Dict[str, int] = {}
    input_format_counts: Dict[str, int] = {}
    quality_tier_counts: Dict[str, int] = {}
    support_kind_counts: Dict[str, int] = {}
    source_table_counts: Dict[str, int] = {}
    unique_fact_ids = set()
    unique_source_refs = set()
    unique_source_records = set()
    passage_anchored_count = 0

    def _count(target: Dict[str, int], value: Any) -> None:
        text = str(value or "").strip()
        if text:
            target[text] = target.get(text, 0) + 1

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        source_ref = str(fact.get("source_ref") or "").strip()
        source_family = str(fact.get("source_family") or "").strip()
        source_record_id = fact.get("source_record_id")
        source_passage = fact.get("source_passage") if isinstance(fact.get("source_passage"), dict) else {}
        if fact_id:
            unique_fact_ids.add(fact_id)
        if source_ref:
            unique_source_refs.add(source_ref)
        if source_family and source_record_id not in (None, ""):
            unique_source_records.add((source_family, str(source_record_id)))
        if source_passage.get("chunk_id") or fact.get("chunk_id"):
            passage_anchored_count += 1
        _count(source_family_counts, source_family)
        _count(record_scope_counts, fact.get("record_scope"))
        _count(artifact_family_counts, fact.get("artifact_family"))
        _count(corpus_family_counts, fact.get("corpus_family"))
        _count(content_origin_counts, fact.get("content_origin"))
        _count(parse_source_counts, fact.get("parse_source"))
        _count(input_format_counts, fact.get("input_format"))
        _count(quality_tier_counts, fact.get("quality_tier"))
        _count(support_kind_counts, fact.get("support_kind"))
        _count(source_table_counts, fact.get("source_table"))

    return {
        "registry_version": "claim_fact_registry_summary.v1",
        "source": "logic_predicate_support_facts",
        "fact_count": len(facts),
        "unique_fact_count": len(unique_fact_ids),
        "unique_source_ref_count": len(unique_source_refs),
        "unique_source_record_count": len(unique_source_records),
        "passage_anchored_count": passage_anchored_count,
        "source_family_counts": source_family_counts,
        "record_scope_counts": record_scope_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
        "parse_source_counts": parse_source_counts,
        "input_format_counts": input_format_counts,
        "quality_tier_counts": quality_tier_counts,
        "support_kind_counts": support_kind_counts,
        "source_table_counts": source_table_counts,
    }


def _summarize_fact_registry_for_predicates(
    predicates: Iterable[Dict[str, Any]],
    *,
    support_facts: Iterable[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    facts: List[Dict[str, Any]] = [fact for fact in support_facts or [] if isinstance(fact, dict)]
    predicate_summaries: List[Dict[str, Any]] = []
    for predicate in predicates or []:
        if not isinstance(predicate, dict):
            continue
        facts.extend(
            fact
            for fact in predicate.get("support_facts", []) or []
            if isinstance(fact, dict)
        )
        if isinstance(predicate.get("fact_registry_summary"), dict):
            predicate_summaries.append(predicate["fact_registry_summary"])
    summary = _summarize_fact_registry_for_facts(facts)
    if facts or not predicate_summaries:
        return summary

    count_map_keys = (
        "source_family_counts",
        "record_scope_counts",
        "artifact_family_counts",
        "corpus_family_counts",
        "content_origin_counts",
        "parse_source_counts",
        "input_format_counts",
        "quality_tier_counts",
        "support_kind_counts",
        "source_table_counts",
    )
    scalar_count_keys = (
        "fact_count",
        "unique_fact_count",
        "unique_source_ref_count",
        "unique_source_record_count",
        "passage_anchored_count",
    )
    for predicate_summary in predicate_summaries:
        for key in scalar_count_keys:
            summary[key] = int(summary.get(key) or 0) + int(predicate_summary.get(key) or 0)
        for key in count_map_keys:
            target = summary.setdefault(key, {})
            source = predicate_summary.get(key) if isinstance(predicate_summary.get(key), dict) else {}
            for value, count in source.items():
                text = str(value or "").strip()
                if text:
                    target[text] = int(target.get(text) or 0) + int(count or 0)
    summary["source"] = "logic_predicate_fact_registry_summary"
    return summary


def _normalize_logic_payload(payload_or_predicates: Any) -> Dict[str, Any]:
    if isinstance(payload_or_predicates, dict):
        raw_predicates = payload_or_predicates.get("predicates")
        predicates = raw_predicates if isinstance(raw_predicates, list) else []
        raw_support_facts = payload_or_predicates.get("support_facts")
        support_facts = [fact for fact in raw_support_facts if isinstance(fact, dict)] if isinstance(raw_support_facts, list) else []
        fact_registry_summary = (
            dict(payload_or_predicates.get("fact_registry_summary"))
            if isinstance(payload_or_predicates.get("fact_registry_summary"), dict)
            else _summarize_fact_registry_for_predicates(predicates, support_facts=support_facts)
        )
        temporal_reasoning_payload = payload_or_predicates.get("temporal_reasoning_payload")
        proof_bundles = _normalize_proof_bundles(payload_or_predicates.get("proof_bundles"))
        if isinstance(temporal_reasoning_payload, dict) and isinstance(temporal_reasoning_payload.get("proof_bundles"), dict):
            proof_bundles.update(_normalize_proof_bundles(temporal_reasoning_payload.get("proof_bundles")))
        temporal_proof_bundle = _normalize_temporal_proof_bundle(payload_or_predicates.get("temporal_proof_bundle"))
        if temporal_proof_bundle:
            key = str(
                temporal_proof_bundle.get("persistence_key")
                or temporal_proof_bundle.get("proof_bundle_id")
                or ""
            ).strip()
            if key:
                proof_bundles[key] = temporal_proof_bundle
        return {
            "predicates": [predicate for predicate in predicates if isinstance(predicate, dict)],
            "support_facts": support_facts,
            "fact_registry_summary": fact_registry_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload if isinstance(temporal_reasoning_payload, dict) else {},
            "proof_bundles": proof_bundles,
            "claim_support_temporal_handoff": _normalize_claim_support_temporal_handoff(
                payload_or_predicates.get("claim_support_temporal_handoff")
            ),
            "claim_reasoning_review": _normalize_claim_reasoning_review(
                payload_or_predicates.get("claim_reasoning_review")
            ),
            "payload_keys": sorted(payload_or_predicates.keys()),
        }

    predicate_list = [predicate for predicate in payload_or_predicates if isinstance(predicate, dict)]
    return {
        "predicates": predicate_list,
        "support_facts": [],
        "fact_registry_summary": _summarize_fact_registry_for_predicates(predicate_list),
        "temporal_reasoning_payload": {},
        "proof_bundles": {},
        "claim_support_temporal_handoff": {},
        "claim_reasoning_review": {},
        "payload_keys": [],
    }


def _build_theorem_export_metadata(claim_support_temporal_handoff: Any) -> Dict[str, Any]:
    handoff = _normalize_claim_support_temporal_handoff(claim_support_temporal_handoff)
    if not handoff:
        return {}
    unresolved_temporal_issue_ids = list(handoff.get("unresolved_temporal_issue_ids", []) or [])
    temporal_issue_ids = list(handoff.get("temporal_issue_ids", []) or [])
    return {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": str(handoff.get("claim_type") or "").strip(),
        "claim_element_id": str(handoff.get("claim_element_id") or "").strip(),
        "chronology_blocked": bool(
            int(handoff.get("unresolved_temporal_issue_count", 0) or 0)
            or unresolved_temporal_issue_ids
            or temporal_issue_ids
        ),
        "chronology_task_count": int(handoff.get("chronology_task_count", 0) or 0),
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "event_ids": list(handoff.get("event_ids", []) or []),
        "temporal_fact_ids": list(handoff.get("temporal_fact_ids", []) or []),
        "temporal_relation_ids": list(handoff.get("temporal_relation_ids", []) or []),
        "timeline_issue_ids": list(handoff.get("timeline_issue_ids", []) or []),
        "temporal_issue_ids": temporal_issue_ids,
        "temporal_proof_bundle_ids": list(handoff.get("temporal_proof_bundle_ids", []) or []),
        "temporal_proof_objectives": list(handoff.get("temporal_proof_objectives", []) or []),
    }


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


def _derive_reasoner_sentence(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
) -> str:
    claim_element_text = ""
    claim_type = ""

    for predicate in predicates:
        if not isinstance(predicate, dict):
            continue
        if str(predicate.get("predicate_type") or "") != "claim_element":
            continue
        claim_element_text = str(predicate.get("claim_element_text") or "").strip()
        claim_type = str(predicate.get("claim_type") or "").strip()
        if claim_element_text:
            break

    if not claim_type:
        claim_types = list(temporal_reasoning_payload.get("claim_types", []) or [])
        claim_type = str(claim_types[0] or "").strip() if claim_types else ""

    seed_text = claim_element_text or claim_type
    seed_text = str(seed_text or "").strip().strip(".")
    if not seed_text:
        return ""

    lowered = seed_text.lower()
    if " shall not " in f" {lowered} " or " shall " in f" {lowered} " or " may " in f" {lowered} ":
        return seed_text if seed_text.endswith(".") else seed_text + "."

    return f"Claimant shall establish {seed_text.lower()}."


def _build_local_proof_artifact(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
    claim_support_temporal_handoff: Dict[str, Any],
    proof_bundles: Dict[str, Dict[str, Any]] | None = None,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Build a deterministic proof artifact from the local temporal bridge.

    The optional upstream reasoner is useful when present, but the adapter
    contract still needs a reviewable proof object in degraded installations.
    This local artifact treats generated TDFOL/DCEC formulas, temporal
    relations, and contradiction signals as the proof basis and exposes the
    same handoff metadata shape used by the upstream bridge.
    """
    predicate_list = [predicate for predicate in predicates if isinstance(predicate, dict)]
    normalized_proof_bundles = _normalize_proof_bundles(proof_bundles)
    theorem_export_metadata = dict(temporal_reasoning_payload.get("theorem_export_metadata") or {})
    handoff = dict(claim_support_temporal_handoff or {})
    tdfol_formulas = [
        str(formula).strip()
        for formula in temporal_reasoning_payload.get("tdfol_formulas", []) or []
        if str(formula).strip()
    ]
    dcec_formulas = [
        str(formula).strip()
        for formula in temporal_reasoning_payload.get("dcec_formulas", []) or []
        if str(formula).strip()
    ]
    contradiction_signals = [
        signal for signal in temporal_reasoning_payload.get("contradiction_signals", []) or []
        if isinstance(signal, dict)
    ]
    proof_basis = {
        "formalism": temporal_reasoning_payload.get("formalism") or "tdfol_dcec_bridge_v1",
        "claim_types": list(temporal_reasoning_payload.get("claim_types", []) or []),
        "predicate_ids": [
            str(predicate.get("predicate_id") or predicate.get("claim_element_id") or "").strip()
            for predicate in predicate_list
            if str(predicate.get("predicate_id") or predicate.get("claim_element_id") or "").strip()
        ],
        "tdfol_formulas": tdfol_formulas,
        "dcec_formulas": dcec_formulas,
        "theorem_export_metadata": theorem_export_metadata,
        "claim_support_temporal_handoff": handoff,
        "proof_bundle_digests": [
            str(bundle.get("bundle_digest") or "").strip()
            for bundle in normalized_proof_bundles.values()
            if str(bundle.get("bundle_digest") or "").strip()
        ],
    }
    proof_id = f"local-proof-{_stable_payload_digest(proof_basis)[:16]}"
    proof_status = "needs_review" if contradiction_signals else "passed"
    violation_count = len(contradiction_signals)
    explanation = {
        "proof_id": proof_id,
        "status": proof_status,
        "proof_execution_source": "local_temporal_bridge",
        "formalism": proof_basis["formalism"],
        "claim_types": proof_basis["claim_types"],
        "tdfol_formula_count": len(tdfol_formulas),
        "dcec_formula_count": len(dcec_formulas),
        "temporal_relation_count": len(temporal_reasoning_payload.get("temporal_relations", []) or []),
        "contradiction_signal_count": violation_count,
        "theorem_export_metadata": theorem_export_metadata,
        "claim_support_temporal_handoff": handoff,
        "reason": reason,
    }
    return {
        "available": True,
        "status": "success",
        "backend": "local_temporal_bridge",
        "reason": reason,
        "sentence": _derive_reasoner_sentence(predicate_list, temporal_reasoning_payload),
        "proof_id": proof_id,
        "proof_status": proof_status,
        "violation_count": violation_count,
        "theorem_export_metadata": theorem_export_metadata,
        "claim_support_temporal_handoff": handoff,
        "explanation": explanation,
        "prover_report": {
            "backend": "local_temporal_bridge",
            "formula_count": len(tdfol_formulas) + len(dcec_formulas),
            "tdfol_formula_count": len(tdfol_formulas),
            "dcec_formula_count": len(dcec_formulas),
            "contradiction_signal_count": violation_count,
        },
        "proof_bundles": deepcopy(normalized_proof_bundles),
    }


def _build_reasoner_proof_artifact(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
    claim_support_temporal_handoff: Dict[str, Any],
    proof_bundles: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if not REASONER_BRIDGE_AVAILABLE or _reasoner_module is None:
        return _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason=str(REASONER_BRIDGE_ERROR or "reasoner_bridge_unavailable"),
        )

    run_pipeline = getattr(_reasoner_module, "run_v2_pipeline_with_defaults", None)
    check_compliance = getattr(_reasoner_module, "check_compliance", None)
    explain_proof = getattr(_reasoner_module, "explain_proof", None)
    if not callable(run_pipeline) or not callable(check_compliance) or not callable(explain_proof):
        return _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason="reasoner_bridge_missing_entrypoints",
        )

    sentence = _derive_reasoner_sentence(predicates, temporal_reasoning_payload)
    if not sentence:
        return _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason="missing_reasoner_sentence",
        )

    theorem_export_metadata = dict(temporal_reasoning_payload.get("theorem_export_metadata") or {})
    normalized_proof_bundles = _normalize_proof_bundles(proof_bundles)
    try:
        pipeline_kwargs = {
            "theorem_export_metadata": theorem_export_metadata,
            "claim_support_temporal_handoff": claim_support_temporal_handoff,
            "proof_bundles": normalized_proof_bundles,
        }
        try:
            supported_parameters = set(inspect.signature(run_pipeline).parameters)
        except (TypeError, ValueError):
            supported_parameters = set()
        if supported_parameters:
            pipeline_kwargs = {
                key: value
                for key, value in pipeline_kwargs.items()
                if key in supported_parameters
            }
        pipeline = run_pipeline(sentence, **pipeline_kwargs)
        compliance = check_compliance(
            {
                "ir": pipeline.get("ir"),
                "facts": {},
                "events": [],
                "theorem_export_metadata": theorem_export_metadata,
                "claim_support_temporal_handoff": claim_support_temporal_handoff,
                "proof_bundles": normalized_proof_bundles,
            },
            {},
        )
        proof_id = str(compliance.get("proof_id") or "").strip()
        explanation = explain_proof(proof_id, format="json") if proof_id else {}
        normalized_explanation = explanation if isinstance(explanation, dict) else {}
        # Provider versions differ in how much context ``explain_proof``
        # returns.  Preserve the adapter contract even when the provider emits
        # only the proof graph.
        normalized_explanation = dict(normalized_explanation)
        normalized_explanation.setdefault("proof_id", proof_id)
        normalized_explanation.setdefault(
            "theorem_export_metadata",
            dict(compliance.get("theorem_export_metadata") or theorem_export_metadata),
        )
        normalized_explanation.setdefault(
            "claim_support_temporal_handoff",
            dict(compliance.get("claim_support_temporal_handoff") or claim_support_temporal_handoff),
        )
        return {
            "available": True,
            "status": "success",
            "sentence": sentence,
            "proof_id": proof_id,
            "proof_status": compliance.get("status"),
            "violation_count": compliance.get("violation_count"),
            "theorem_export_metadata": dict(compliance.get("theorem_export_metadata") or theorem_export_metadata),
            "claim_support_temporal_handoff": dict(
                compliance.get("claim_support_temporal_handoff") or claim_support_temporal_handoff
            ),
            "explanation": normalized_explanation,
            "prover_report": dict(pipeline.get("prover_report") or {}),
            "proof_bundles": deepcopy(normalized_proof_bundles),
        }
    except Exception as exc:
        local_artifact = _build_local_proof_artifact(
            predicates,
            temporal_reasoning_payload,
            claim_support_temporal_handoff,
            proof_bundles,
            reason=str(exc),
        )
        local_artifact["upstream_error"] = str(exc)
        local_artifact["sentence"] = sentence
        return local_artifact


def _summarize_predicates(predicates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    predicate_list: List[Dict[str, Any]] = [
        predicate for predicate in predicates
        if isinstance(predicate, dict)
    ]
    predicate_type_counts: Counter[str] = Counter()
    claim_type_counts: Counter[str] = Counter()
    temporal_predicate_count = 0
    temporal_relation_count = 0
    contradiction_signal_count = 0

    for predicate in predicate_list:
        predicate_type = str(predicate.get("predicate_type") or "unknown").strip() or "unknown"
        predicate_type_counts[predicate_type] += 1
        claim_type = str(predicate.get("claim_type") or "").strip()
        if claim_type:
            claim_type_counts[claim_type] += 1
        if predicate_type.startswith("temporal_"):
            temporal_predicate_count += 1
        if predicate_type == "temporal_relation":
            temporal_relation_count += 1
        if predicate_type in {"contradiction_candidate", "temporal_issue"}:
            contradiction_signal_count += 1

    return {
        "predicate_count": len(predicate_list),
        "predicate_type_counts": dict(sorted(predicate_type_counts.items())),
        "claim_type_counts": dict(sorted(claim_type_counts.items())),
        "temporal_predicate_count": temporal_predicate_count,
        "temporal_relation_count": temporal_relation_count,
        "contradiction_signal_count": contradiction_signal_count,
    }


def _build_local_logic_snapshot(temporal_reasoning_payload: Dict[str, Any]) -> Dict[str, Any]:
    frame_kb = FrameKnowledgeBase()

    for claim in temporal_reasoning_payload.get("claim_elements", []) or []:
        claim_symbol = str(claim.get("claim_symbol") or "claim_unknown")
        frame_name = str(claim.get("claim_element_text") or claim_symbol)
        for slot in ("claim_type", "claim_element_id", "coverage_status"):
            value = claim.get(slot)
            if value:
                frame_kb.add_fact(claim_symbol, frame_name, slot, value, "claim_element")

    for trace in temporal_reasoning_payload.get("support_traces", []) or []:
        trace_symbol = str(trace.get("support_symbol") or "support_unknown")
        frame_name = str(trace.get("text") or trace_symbol)
        for slot in ("claim_type", "support_ref", "support_kind"):
            value = trace.get(slot)
            if value:
                frame_kb.add_fact(trace_symbol, frame_name, slot, value, "support_trace")

    for event in temporal_reasoning_payload.get("timeline_events", []) or []:
        event_symbol = str(event.get("event_symbol") or "event_unknown")
        frame_name = str(event.get("text") or event_symbol)
        for slot in ("claim_type", "fact_id", "fact_type", "start_date", "end_date", "granularity"):
            value = event.get(slot)
            if value:
                frame_kb.add_fact(event_symbol, frame_name, slot, value, "temporal_fact")
        for marker in event.get("relative_markers", []) or []:
            frame_kb.add_fact(event_symbol, frame_name, "relative_marker", marker, "temporal_fact")

    for relation in temporal_reasoning_payload.get("temporal_relations", []) or []:
        relation_symbol = str(relation.get("relation_id") or relation.get("relation_type") or "relation_unknown")
        frame_name = str(relation.get("relation_type") or relation_symbol)
        for slot in ("claim_type", "relation_type", "source_event_symbol", "target_event_symbol"):
            value = relation.get(slot)
            if value:
                frame_kb.add_fact(relation_symbol, frame_name, slot, value, "temporal_relation")

    for signal in temporal_reasoning_payload.get("contradiction_signals", []) or []:
        signal_symbol = str(signal.get("signal_symbol") or "signal_unknown")
        frame_name = str(signal.get("summary") or signal.get("issue_type") or signal_symbol)
        for slot in ("claim_type", "predicate_type", "issue_type", "severity"):
            value = signal.get(slot)
            if value:
                frame_kb.add_fact(signal_symbol, frame_name, slot, value, "contradiction_signal")

    return {
        "frame_count": frame_kb.frame_count(),
        "frames": frame_kb.to_dict(),
    }


# ---------------------------------------------------------------------------
# Local FOL extraction helpers (regex-based fallback when ipfs_datasets_py
# logic modules are absent or have not yet been populated by the submodule).
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_NAMED_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
_VERB_PHRASE_RE = re.compile(
    r"\b(report(?:ed)?|terminat(?:ed)?|discriminat(?:ed)?|retaliat(?:ed)?|"
    r"violat(?:ed)?|breach(?:ed)?|fail(?:ed)?|notif(?:ied)?|request(?:ed)?|"
    r"deny|denied|harm(?:ed)?|seek(?:s)?|allege(?:s)?)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2}(?:,?\s+\d{4})?"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)


def _local_extract_fol_predicates(text: str) -> List[Dict[str, Any]]:
    """Extract simple FOL-style predicates from *text* using regex heuristics.

    Returns a list of predicate dicts compatible with the rest of the logic
    pipeline.  Each dict carries at minimum ``predicate_type``, ``formula``,
    and ``source_sentence``.
    """
    predicates: List[Dict[str, Any]] = []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for index, sentence in enumerate(sentences, start=1):
        entities = _NAMED_ENTITY_RE.findall(sentence)
        verbs = _VERB_PHRASE_RE.findall(sentence)
        dates = _DATE_RE.findall(sentence)

        for verb in verbs:
            subj = entities[0] if entities else "Unknown"
            obj = entities[1] if len(entities) > 1 else "party"
            predicate_symbol = _normalize_logic_symbol(f"{verb}_{index}", prefix="pred")
            predicates.append(
                {
                    "predicate_type": "factual_statement",
                    "formula": f"{verb.capitalize()}({_normalize_logic_symbol(subj, prefix='e')},{_normalize_logic_symbol(obj, prefix='e')})",
                    "symbol": predicate_symbol,
                    "source_sentence": sentence,
                    "entities": entities[:4],
                    "verb": verb.lower(),
                }
            )

        for date in dates:
            temporal_symbol = _normalize_logic_symbol(f"temporal_{index}", prefix="t")
            predicates.append(
                {
                    "predicate_type": "temporal_fact",
                    "formula": f"AtTime({temporal_symbol},{_normalize_time_symbol(date)})",
                    "symbol": temporal_symbol,
                    "source_sentence": sentence,
                    "date_expression": date,
                }
            )

    return predicates


# ---------------------------------------------------------------------------
# Local deontic extraction helpers
# ---------------------------------------------------------------------------

_DEONTIC_PATTERNS: List[tuple[str, str, re.Pattern[str]]] = [
    ("prohibition", "F",
     re.compile(r"\b(must not|shall not|may not|cannot|can not|will not|is prohibited from|is forbidden to)\b", re.I)),
    ("obligation", "O",
     re.compile(r"\b(must|shall|required to|is required to|has a duty to|ought to)\b", re.I)),
    ("permission", "P",
     re.compile(r"\b(may|is permitted to|is allowed to|is entitled to|has the right to)\b", re.I)),
]


def _local_extract_deontic_norms(text: str) -> List[Dict[str, Any]]:
    """Extract deontic norms from *text* using pattern matching."""
    norms: List[Dict[str, Any]] = []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for index, sentence in enumerate(sentences, start=1):
        for norm_type, modality_symbol, pattern in _DEONTIC_PATTERNS:
            match = pattern.search(sentence)
            if match:
                entities = _NAMED_ENTITY_RE.findall(sentence)
                actor = entities[0] if entities else "actor"
                actor_sym = _normalize_logic_symbol(actor, prefix="a")
                norm_symbol = _normalize_logic_symbol(f"{norm_type}_{index}", prefix="norm")
                verb_rest = sentence[match.end():].strip().rstrip(".,;") or "perform_action"
                action_sym = _normalize_logic_symbol(verb_rest[:40], prefix="act")
                norms.append(
                    {
                        "norm_type": norm_type,
                        "modality": modality_symbol,
                        "formula": f"{modality_symbol}({actor_sym},{action_sym})",
                        "symbol": norm_symbol,
                        "actor": actor,
                        "action_text": verb_rest[:80],
                        "source_sentence": sentence,
                        "trigger_keyword": match.group(0),
                    }
                )
                break
    return norms


def text_to_fol(
    text: str,
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Convert *text* to First-Order Logic predicates.

    Tries the ``ipfs_datasets_py.logic.fol.FOLConverter`` from the submodule
    first.  Falls back to local regex-based extraction when the upstream
    module is unavailable.
    """
    capability = get_logic_capability(FormalLogicOperation.TEXT_TO_FOL)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    # --- Try upstream FOLConverter (sync path) ---
    if _fol_module is not None:
        try:
            FOLConverter = getattr(_fol_module, "FOLConverter", None)
            if FOLConverter is None:
                # Older module layout: fol is a directory package
                fol_converter_mod, _ = import_module_optional("ipfs_datasets_py.logic.fol.converter")
                if fol_converter_mod is not None:
                    FOLConverter = getattr(fol_converter_mod, "FOLConverter", None)
            if FOLConverter is not None:
                converter = FOLConverter(use_nlp=False, use_cache=False)
                result = converter.convert(str(text or ""))
                raw_predicates = []
                if hasattr(result, "output") and result.output is not None:
                    output = result.output
                    if hasattr(output, "predicates"):
                        raw_predicates = [
                            {
                                "predicate_type": "factual_statement",
                                "formula": str(p) if not isinstance(p, dict) else str(p.get("formula", p)),
                                "symbol": _normalize_logic_symbol(str(p)[:30], prefix="pred"),
                            }
                            for p in (output.predicates or [])
                        ]
                return with_adapter_metadata(
                    {
                        "status": "success",
                        "predicates": raw_predicates,
                        "source_text": str(text or ""),
                        "converter": "FOLConverter",
                        "capability": capability.as_dict(),
                    },
                    operation="text_to_fol",
                    backend_available=capability.available,
                    degraded_reason=capability.reason,
                    implementation_status=implementation_status,
                    extra_metadata={
                        "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
                        "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
                        **_logic_operation_metadata(capability),
                        "logic_path": "logic.fol",
                    },
                )
        except Exception:
            pass

    # --- Local regex fallback ---
    predicates = _local_extract_fol_predicates(str(text or ""))
    return with_adapter_metadata(
        {
            "status": "success" if capability.available else capability.state.value,
            "predicates": predicates,
            "source_text": str(text or ""),
            "converter": "local_regex_fallback",
            "capability": capability.as_dict(),
        },
        operation="text_to_fol",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            **_logic_operation_metadata(capability),
            "logic_path": "logic.fol" if _fol_module is not None else "local",
        },
    )


def legal_text_to_deontic(
    text: str,
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Convert legal *text* to deontic logic norms.

    Tries ``ipfs_datasets_py.logic.deontic.DeonticConverter`` first, then
    supplements (or falls back) to local pattern-based extraction.

    The upstream converter returns a single ``DeonticFormula`` per call.  We
    wrap it into the same list format as the local extractor.  When the
    upstream result is empty the local extractor is used as a supplement so
    that well-known prohibition/obligation patterns are never silently dropped.
    """
    capability = get_logic_capability(FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    upstream_norms: List[Dict[str, Any]] = []
    upstream_available = False

    # --- Try upstream DeonticConverter (sync path) ---
    if _deontic_module is not None:
        try:
            DeonticConverter = getattr(_deontic_module, "DeonticConverter", None)
            if DeonticConverter is None:
                deontic_conv_mod, _ = import_module_optional(
                    "ipfs_datasets_py.logic.deontic.converter"
                )
                if deontic_conv_mod is not None:
                    DeonticConverter = getattr(deontic_conv_mod, "DeonticConverter", None)
            if DeonticConverter is not None:
                converter = DeonticConverter(jurisdiction="us", document_type="general")
                result = converter.convert(str(text or ""))
                if hasattr(result, "output") and result.output is not None:
                    output = result.output
                    # DeonticFormula is a single formula object — wrap it.
                    if hasattr(output, "operator") and hasattr(output, "proposition"):
                        raw_op = getattr(output, "operator", None)
                        # Handle enum objects: prefer .value, then fall back to str.
                        op_value = str(getattr(raw_op, "value", raw_op) or "")
                        modality_map = {"O": "obligation", "P": "permission", "F": "prohibition"}
                        upstream_norms = [
                            {
                                "norm_type": modality_map.get(op_value, "obligation"),
                                "modality": op_value,
                                "formula": str(output.formula) if hasattr(output, "formula") else str(output),
                                "source_text": str(getattr(output, "source_text", "")),
                                "converter": "DeonticConverter",
                            }
                        ]
                    elif hasattr(output, "formulas"):
                        # DeonticFormulaSet
                        for f in (output.formulas or []):
                            op_val = str(getattr(getattr(f, "operator", None), "value", "") or "")
                            modality_map = {"O": "obligation", "P": "permission", "F": "prohibition"}
                            upstream_norms.append(
                                {
                                    "norm_type": modality_map.get(op_val, "obligation"),
                                    "modality": op_val,
                                    "formula": str(f.formula) if hasattr(f, "formula") else str(f),
                                    "source_text": str(getattr(f, "source_text", "")),
                                    "converter": "DeonticConverter",
                                }
                            )
                    elif hasattr(output, "norms"):
                        for n in (output.norms or []):
                            upstream_norms.append(
                                {
                                    "norm_type": str(getattr(n, "norm_type", "obligation")),
                                    "modality": str(getattr(n, "modality", "O")),
                                    "formula": str(getattr(n, "formula", n)),
                                    "source_text": str(getattr(n, "source_text", "")),
                                    "converter": "DeonticConverter",
                                }
                            )
                upstream_available = True
        except Exception:
            pass

    # --- Local pattern extraction ---
    local_norms = _local_extract_deontic_norms(str(text or ""))

    # Use upstream if it found norms, otherwise supplement with local patterns.
    if upstream_norms:
        norms = upstream_norms
        converter_used = "DeonticConverter"
    else:
        norms = local_norms
        converter_used = "local_pattern_fallback"

    return with_adapter_metadata(
        {
            "status": "success" if capability.available else capability.state.value,
            "norms": norms,
            "source_text": str(text or ""),
            "converter": converter_used,
            "capability": capability.as_dict(),
        },
        operation="legal_text_to_deontic",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            **_logic_operation_metadata(capability),
            "logic_path": "logic.deontic" if _deontic_module is not None else "local",
        },
    )


def prove_claim_elements(
    predicates: Iterable[Dict[str, Any]] | Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Prove or refute claim elements by running the hybrid reasoning pipeline.

    Delegates to :func:`run_hybrid_reasoning` so that both the upstream
    ``hybrid_v2_blueprint`` reasoner bridge *and* the local TDFOL/DCEC bridge
    are tried in priority order.  The return value includes ``provable_elements``
    and ``unprovable_elements`` extracted from the proof artifact.

    Contradiction detection is performed by :func:`check_contradictions` and
    the count is included as ``contradiction_count`` in the result.
    """
    capability = get_logic_capability(FormalLogicOperation.PROVE_CLAIM_ELEMENTS)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    fact_registry_summary = normalized_payload["fact_registry_summary"]
    proof_bundles = normalized_payload["proof_bundles"]

    # Run the full hybrid reasoning pipeline (handles reasoner bridge + fallback).
    reasoning_result = run_hybrid_reasoning(normalized_payload)
    result_inner = dict(reasoning_result.get("result") or {})
    proof_artifact = dict(result_inner.get("proof_artifact") or {})
    temporal_reasoning_payload = dict(reasoning_result.get("temporal_reasoning_payload") or {})

    proof_status = str(
        proof_artifact.get("proof_status")
        or proof_artifact.get("status")
        or "needs_review"
    )
    # Normalise status values from the reasoner bridge that should be treated
    # as "needs_review" rather than propagated as opaque strings.
    if proof_status in ("unavailable", "pending", "not_implemented", ""):
        proof_status = "needs_review"
    violation_count = int(proof_artifact.get("violation_count") or 0)

    # Run check_contradictions for a precise contradiction count that includes
    # both temporal-signal contradictions and formula-level negation pairs.
    contradiction_result = check_contradictions(normalized_payload)
    contradiction_count = int(contradiction_result.get("contradiction_count") or 0)
    contradiction_list = list(contradiction_result.get("contradictions") or [])
    # Escalate proof_status to needs_review when contradictions are found.
    if contradiction_count and proof_status == "passed":
        proof_status = "needs_review"

    # Classify each predicate as provable / unprovable based on proof status.
    # claim_element predicates are classified as provable only when their coverage
    # status is 'supported'; partially-supported or missing elements are *not*
    # classified as unprovable here, because those gaps are already tracked by the
    # missing_support_kind proof gap mechanism and would otherwise create duplicate
    # "logic_unprovable" proof gaps for what is really a support-coverage gap.
    # Unprovable classification is reserved for explicit reasoner failures
    # (proof_status == "failed") rather than partial-coverage situations.
    provable_elements: List[Dict[str, Any]] = []
    unprovable_elements: List[Dict[str, Any]] = []
    for pred in predicate_list:
        pred_type = str(pred.get("predicate_type") or "")
        if pred_type == "claim_element":
            coverage = str(pred.get("coverage_status") or "").strip().lower()
            if coverage == "supported":
                provable_elements.append(pred)
            elif proof_status == "failed":
                # Only flag as unprovable when the reasoner explicitly rejected the
                # predicate; a missing/partial coverage status is not a logic failure.
                unprovable_elements.append(pred)

    # Export TDFOL/DCEC formulas to Lean 4 and Coq theorem stubs.
    theorem_export: Dict[str, Any] = {}
    try:
        from .theorem_export import export_proof_result_to_theorems

        theorem_export = export_proof_result_to_theorems(
            {
                "temporal_reasoning_payload": temporal_reasoning_payload,
                "proof_artifact": proof_artifact,
                "proof_bundles": proof_bundles,
            },
        )
    except Exception:
        pass

    return with_adapter_metadata(
        {
            "status": (
                "success"
                if capability.available and proof_status not in {"error", "failed"}
                else capability.state.value
                if not capability.available
                else "error"
            ),
            "provable_elements": provable_elements,
            "unprovable_elements": unprovable_elements,
            "proof_status": proof_status,
            "violation_count": violation_count,
            "contradiction_count": contradiction_count,
            "contradictions": contradiction_list,
            **predicate_summary,
            "fact_registry_summary": deepcopy(fact_registry_summary),
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "capability": capability.as_dict(),
            "proof_bundles": deepcopy(proof_bundles),
            "proof_artifact": proof_artifact,
            "theorem_export": theorem_export,
        },
        operation="prove_claim_elements",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            **predicate_summary,
            "fact_registry_summary": deepcopy(fact_registry_summary),
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_bundles": deepcopy(proof_bundles),
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            "logic_path": _selected_logic_path(
                (_integration_module, "logic.integration"),
                (_external_provers_module, "logic.external_provers"),
                (_tdfol_module, "logic.TDFOL"),
                (_fol_module, "logic.fol"),
                (_deontic_module, "logic.deontic"),
            ),
            "reasoner_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "theorem_export_version": theorem_export.get("export_version") or "",
            **_logic_operation_metadata(capability),
        },
    )


def _detect_formula_contradictions(formulas: List[str]) -> List[Dict[str, Any]]:
    """Detect simple A / not-A formula contradictions in *formulas*.

    A contradiction is flagged when the formula list contains both a positive
    assertion ``Pred(x,y)`` and its negation ``not(Pred(x,y))`` or a
    ``Conflict(x,y)`` entry that references known predicates.

    Returns a list of contradiction dicts compatible with the unified
    ``contradictions`` schema.
    """
    contradictions: List[Dict[str, Any]] = []
    positive: Dict[str, str] = {}
    negative: Dict[str, str] = {}
    conflict_pairs: List[Tuple[str, str]] = []

    _not_re = re.compile(r"^not\((.+)\)$", re.IGNORECASE)
    _conflict_re = re.compile(r"^Conflict\(([^,]+),([^)]+)\)$", re.IGNORECASE)

    for formula in formulas:
        formula = formula.strip()
        not_match = _not_re.match(formula)
        if not_match:
            inner = not_match.group(1).strip()
            negative[inner] = formula
            if inner in positive:
                contradictions.append(
                    {
                        "contradiction_id": f"formula-{len(contradictions) + 1}",
                        "type": "formula_negation",
                        "positive_formula": positive[inner],
                        "negative_formula": formula,
                        "summary": f"Contradiction: {inner} and not({inner})",
                        "severity": "error",
                    }
                )
        else:
            conflict_match = _conflict_re.match(formula)
            if conflict_match:
                left = conflict_match.group(1).strip()
                right = conflict_match.group(2).strip()
                conflict_pairs.append((left, right))
            else:
                positive[formula] = formula
                if formula in negative:
                    contradictions.append(
                        {
                            "contradiction_id": f"formula-{len(contradictions) + 1}",
                            "type": "formula_negation",
                            "positive_formula": formula,
                            "negative_formula": negative[formula],
                            "summary": f"Contradiction: {formula} and not({formula})",
                            "severity": "error",
                        }
                    )

    for left, right in conflict_pairs:
        contradictions.append(
            {
                "contradiction_id": f"conflict-{len(contradictions) + 1}",
                "type": "temporal_conflict",
                "left_symbol": left,
                "right_symbol": right,
                "summary": f"Temporal conflict between {left} and {right}",
                "severity": "warning",
            }
        )

    return contradictions


def _run_local_z3_check(
    tdfol_formulas: List[str],
    contradictions: List[Dict[str, Any]],
    z3_mod: Any,
) -> None:
    """Use the standalone z3-solver package to check formula satisfiability.

    This is called when the ipfs_datasets_py Z3 bridge is absent but the
    ``z3-solver`` PyPI package is installed.  The approach is conservative:

    * Each TDFOL formula string is parsed as a simple boolean variable
      (``z3.Bool``).  Formulas whose negations are both present in the set
      trigger an UNSAT result via the local :func:`_detect_formula_contradictions`
      helper — that part is already handled by step 2/3 above.
    * For conjunction formulas (``A and B``) we add both conjuncts as separate
      assertions so Z3 can derive conflicts between them.

    If Z3 reports UNSAT for the resulting assertion set we append a
    ``smt_unsat`` entry to *contradictions*.
    """
    Bool = getattr(z3_mod, "Bool", None)
    Solver = getattr(z3_mod, "Solver", None)
    unsat_const = getattr(z3_mod, "unsat", None)
    if not callable(Bool) or not callable(Solver) or unsat_const is None:
        return

    solver = Solver()
    # Pre-compute all normalised atom names in a set for O(1) negation lookup.
    all_atom_names = {
        re.sub(r"[^A-Za-z0-9_]", "_", f.strip())[:_Z3_ATOM_NAME_MAX_LENGTH]
        for f in tdfol_formulas
    }
    for formula in tdfol_formulas:
        # Represent each atomic formula as a fresh Boolean variable named
        # after the formula string (truncated to avoid Z3 identifier limits).
        atom_name = re.sub(r"[^A-Za-z0-9_]", "_", formula.strip())[:_Z3_ATOM_NAME_MAX_LENGTH]
        if not atom_name:
            continue
        var = Bool(atom_name)
        solver.add(var)
        # If the formula set already contains the negation of this formula
        # we add its negation as a second assertion so Z3 can derive UNSAT.
        neg_name = re.sub(r"[^A-Za-z0-9_]", "_", f"not({formula.strip()})")[:_Z3_ATOM_NAME_MAX_LENGTH]
        if neg_name in all_atom_names:
            neg_var = Bool(neg_name)
            solver.add(neg_var)

    if solver.check() == unsat_const:
        contradictions.append(
            {
                "contradiction_id": f"z3-local-{len(contradictions) + 1}",
                "type": "smt_unsat",
                "summary": "Z3 SMT solver (local z3-solver) reports formula set is unsatisfiable",
                "severity": "error",
                "z3_backend": "z3-solver",
            }
        )


def check_contradictions(
    predicates: Iterable[Dict[str, Any]] | Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Check *predicates* for logical contradictions.

    Detection strategy (applied in order, results merged):

    1. **Contradiction-signal predicates** — predicates with
       ``predicate_type`` of ``temporal_issue`` or
       ``contradiction_candidate`` are surfaced directly.
    2. **Formula-level negation** — pairs ``P(x)`` / ``not(P(x))`` in the
       TDFOL formula set generated by the temporal bridge.
    3. **Conflict formulas** — any ``Conflict(a,b)`` entry emitted by the
       temporal bridge for temporal ordering violations.
    4. **Z3 SMT prover** (when ``ipfs_datasets_py`` Z3 bridge is available) —
       the formula set is submitted to the SMT prover for a satisfiability
       check; an UNSAT result is reported as a contradiction.

    Returns a dict with:

    * ``contradictions`` — list of contradiction dicts (typed, with
      ``contradiction_id``, ``type``, ``summary``, ``severity``)
    * ``contradiction_count`` — integer count
    * ``has_contradictions`` — bool
    * ``proof_status`` — ``"passed"`` (no contradictions found),
      ``"needs_review"`` (signals present but not proven), or ``"error"``
    """
    capability = get_logic_capability(FormalLogicOperation.CHECK_CONTRADICTIONS)
    if require_implemented:
        capability.require_implemented()
    implementation_status = (
        "implemented" if capability.available else capability.state.value
    )
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    proof_bundles = normalized_payload["proof_bundles"]
    temporal_reasoning_payload = _build_temporal_reasoning_payload(
        predicate_list,
        claim_support_temporal_handoff=normalized_payload["claim_support_temporal_handoff"],
        claim_reasoning_review=normalized_payload["claim_reasoning_review"],
        proof_bundles=proof_bundles,
    )

    contradictions: List[Dict[str, Any]] = []

    # 1. Contradiction-signal predicates (temporal_issue / contradiction_candidate)
    for signal in temporal_reasoning_payload.get("contradiction_signals") or []:
        contradictions.append(
            {
                "contradiction_id": f"signal-{len(contradictions) + 1}",
                "type": str(signal.get("predicate_type") or "temporal_issue"),
                "issue_type": str(signal.get("issue_type") or ""),
                "summary": str(signal.get("summary") or "temporal contradiction signal"),
                "severity": str(signal.get("severity") or "warning"),
                "claim_type": str(signal.get("claim_type") or ""),
                "signal_symbol": str(signal.get("signal_symbol") or ""),
            }
        )

    # 2 & 3. Formula-level negation and Conflict() pairs from TDFOL bridge
    tdfol_formulas: List[str] = list(temporal_reasoning_payload.get("tdfol_formulas") or [])
    contradictions.extend(_detect_formula_contradictions(tdfol_formulas))

    # 4. Z3 SMT prover (optional, additive)
    # Tries the ipfs_datasets_py bridge first, then falls back to the
    # standalone z3-solver package if available.
    if _z3_module is not None:
        try:
            z3_check = getattr(_z3_module, "check_satisfiability", None)
            if callable(z3_check) and tdfol_formulas:
                z3_result = z3_check(tdfol_formulas)
                if isinstance(z3_result, dict) and z3_result.get("satisfiable") is False:
                    contradictions.append(
                        {
                            "contradiction_id": f"z3-{len(contradictions) + 1}",
                            "type": "smt_unsat",
                            "summary": "Z3 SMT solver reports formula set is unsatisfiable",
                            "severity": "error",
                            "z3_result": z3_result,
                        }
                    )
        except Exception:
            pass
    elif _local_z3_module is not None and tdfol_formulas:
        # Local z3-solver fallback: build a simple uninterpreted-function
        # model and check satisfiability of the formula set parsed as
        # assertion strings via z3.parse_smt2_string when possible.
        try:
            _run_local_z3_check(tdfol_formulas, contradictions, _local_z3_module)
        except Exception:
            pass

    proof_status = "passed" if not contradictions else "needs_review"

    return with_adapter_metadata(
        {
            "status": "success" if capability.available else capability.state.value,
            "contradictions": contradictions,
            "contradiction_count": len(contradictions),
            "has_contradictions": bool(contradictions),
            "proof_status": proof_status,
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_bundles": deepcopy(proof_bundles),
            "capability": capability.as_dict(),
        },
        operation="check_contradictions",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=implementation_status,
        extra_metadata={
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_bundles": deepcopy(proof_bundles),
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            **_logic_operation_metadata(capability),
        },
    )


def run_hybrid_reasoning(
    payload: Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Run the local temporal bridge under an explicit capability contract."""

    capability = get_logic_capability(FormalLogicOperation.RUN_HYBRID_REASONING)
    if require_implemented:
        capability.require_implemented()
    normalized_payload = _normalize_logic_payload(payload)
    predicates = normalized_payload["predicates"]
    bridge_payload = normalized_payload["temporal_reasoning_payload"]
    claim_support_temporal_handoff = normalized_payload["claim_support_temporal_handoff"]
    claim_reasoning_review = normalized_payload["claim_reasoning_review"]
    proof_bundles = normalized_payload["proof_bundles"]
    predicate_summary = _summarize_predicates(predicates)
    fact_registry_summary = normalized_payload["fact_registry_summary"]

    if isinstance(bridge_payload, dict) and bridge_payload:
        temporal_reasoning_payload = deepcopy(bridge_payload)
    else:
        temporal_reasoning_payload = _build_temporal_reasoning_payload(
            predicates,
            claim_support_temporal_handoff=claim_support_temporal_handoff,
            claim_reasoning_review=claim_reasoning_review,
            proof_bundles=proof_bundles,
        )

    if proof_bundles:
        bundle_formula_payload = _extract_formula_payload_from_proof_bundles(proof_bundles)
        if bundle_formula_payload["tdfol_formulas"] or bundle_formula_payload["dcec_formulas"]:
            temporal_reasoning_payload["tdfol_formulas"] = bundle_formula_payload["tdfol_formulas"]
            temporal_reasoning_payload["dcec_formulas"] = bundle_formula_payload["dcec_formulas"]
            temporal_reasoning_payload["tdfol_formula_count"] = len(bundle_formula_payload["tdfol_formulas"])
            temporal_reasoning_payload["dcec_formula_count"] = len(bundle_formula_payload["dcec_formulas"])
            temporal_reasoning_payload["tdfol_formula_certainties"] = bundle_formula_payload["tdfol_formula_certainties"]
            temporal_reasoning_payload["dcec_formula_certainties"] = bundle_formula_payload["dcec_formula_certainties"]
        temporal_reasoning_payload["proof_bundles"] = deepcopy(proof_bundles)
        temporal_reasoning_payload["proof_execution_source"] = "temporal_proof_bundle"
        if bundle_formula_payload["theorem_export_metadata"]:
            temporal_reasoning_payload["theorem_export_metadata"] = bundle_formula_payload["theorem_export_metadata"]

    if claim_support_temporal_handoff and not isinstance(
        temporal_reasoning_payload.get("claim_support_temporal_handoff"),
        dict,
    ):
        temporal_reasoning_payload["claim_support_temporal_handoff"] = claim_support_temporal_handoff
    if claim_support_temporal_handoff and not isinstance(
        temporal_reasoning_payload.get("theorem_export_metadata"),
        dict,
    ):
        temporal_reasoning_payload["theorem_export_metadata"] = _build_theorem_export_metadata(
            claim_support_temporal_handoff
        )
    if claim_reasoning_review and not isinstance(
        temporal_reasoning_payload.get("claim_reasoning_review"),
        dict,
    ):
        temporal_reasoning_payload["claim_reasoning_review"] = deepcopy(claim_reasoning_review)
    if fact_registry_summary and not isinstance(
        temporal_reasoning_payload.get("fact_registry_summary"),
        dict,
    ):
        temporal_reasoning_payload["fact_registry_summary"] = deepcopy(fact_registry_summary)

    proof_artifact = _build_reasoner_proof_artifact(
        predicates,
        temporal_reasoning_payload,
        claim_support_temporal_handoff,
        proof_bundles,
    )
    local_logic_snapshot = _build_local_logic_snapshot(temporal_reasoning_payload)

    result_payload = {
        "status": "success",
        "capability": capability.as_dict(),
        "result": {
            "formalism": temporal_reasoning_payload.get("formalism") or "tdfol_dcec_bridge_v1",
            "claim_types": list(temporal_reasoning_payload.get("claim_types", []) or []),
            "tdfol_formulas": list(temporal_reasoning_payload.get("tdfol_formulas", []) or []),
            "dcec_formulas": list(temporal_reasoning_payload.get("dcec_formulas", []) or []),
            "theorem_export_metadata": dict(temporal_reasoning_payload.get("theorem_export_metadata") or {}),
            "proof_execution_source": str(temporal_reasoning_payload.get("proof_execution_source") or "predicates"),
            "proof_bundles": deepcopy(proof_bundles),
            "timeline_event_count": len(temporal_reasoning_payload.get("timeline_events", []) or []),
            "temporal_relation_count": len(temporal_reasoning_payload.get("temporal_relations", []) or []),
            "contradiction_signal_count": len(temporal_reasoning_payload.get("contradiction_signals", []) or []),
            "reasoning_mode": "temporal_bridge",
            "compiler_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "proof_artifact": proof_artifact,
            "local_logic_snapshot": local_logic_snapshot,
            "fact_registry_summary": deepcopy(fact_registry_summary),
            "claim_reasoning_review": deepcopy(temporal_reasoning_payload.get("claim_reasoning_review") or {}),
            "compiler_bridge_path": (
                REASONER_BRIDGE_PATH if REASONER_BRIDGE_AVAILABLE else ""
            ),
        },
        "payload_keys": normalized_payload["payload_keys"],
        "predicate_count": predicate_summary.get("predicate_count", 0),
        "fact_registry_summary": deepcopy(fact_registry_summary),
        "proof_bundles": deepcopy(proof_bundles),
        "temporal_reasoning_payload": temporal_reasoning_payload,
    }
    return with_adapter_metadata(
        result_payload,
        operation="run_hybrid_reasoning",
        backend_available=capability.available,
        degraded_reason=str(REASONER_BRIDGE_ERROR) if REASONER_BRIDGE_ERROR and not REASONER_BRIDGE_AVAILABLE else None,
        implementation_status=capability.state.value,
        extra_metadata={
            **predicate_summary,
            "reasoning_mode": "temporal_bridge",
            "compiler_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "compiler_bridge_path": (
                REASONER_BRIDGE_PATH if REASONER_BRIDGE_AVAILABLE else ""
            ),
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            "local_logic_snapshot_frame_count": local_logic_snapshot["frame_count"],
            **_logic_operation_metadata(capability),
            "proof_bundle_count": len(proof_bundles),
        },
    )


def export_theorem_from_proof_bundle(
    proof_bundle: Dict[str, Any],
    *,
    exported_at: str = "1970-01-01T00:00:00+00:00",
) -> Dict[str, Any]:
    """Recreate Lean/Coq theorem exports from a persisted temporal proof bundle.

    The function is deterministic by default: if callers do not supply
    ``exported_at`` the same persisted bundle produces byte-identical theorem
    sources across runs.  The bundle's formulas, metadata, certainties, and
    digest are preserved in the returned export payload.
    """
    bundle = _normalize_temporal_proof_bundle(proof_bundle)
    theorem_exports = bundle.get("theorem_exports") if isinstance(bundle.get("theorem_exports"), dict) else {}
    tdfol_formulas = [
        str(formula).strip()
        for formula in theorem_exports.get("tdfol_formulas", []) or []
        if str(formula).strip()
    ]
    dcec_formulas = [
        str(formula).strip()
        for formula in theorem_exports.get("dcec_formulas", []) or []
        if str(formula).strip()
    ]
    theorem_export_metadata = (
        deepcopy(theorem_exports.get("theorem_export_metadata"))
        if isinstance(theorem_exports.get("theorem_export_metadata"), dict)
        else {}
    )
    theorem_export_metadata["proof_execution_source"] = "temporal_proof_bundle"
    theorem_export_metadata["proof_bundle_digest"] = bundle.get("bundle_digest", "")

    from .theorem_export import export_proof_result_to_theorems

    theorem_export = export_proof_result_to_theorems(
        {
            "temporal_reasoning_payload": {
                "formalism": "tdfol_dcec_bridge_v1",
                "tdfol_formulas": tdfol_formulas,
                "dcec_formulas": dcec_formulas,
                "tdfol_formula_certainties": deepcopy(theorem_exports.get("tdfol_formula_certainties") or {}),
                "dcec_formula_certainties": deepcopy(theorem_exports.get("dcec_formula_certainties") or {}),
                "theorem_export_metadata": theorem_export_metadata,
                "proof_bundles": {
                    str(bundle.get("persistence_key") or bundle.get("proof_bundle_id") or "bundle"): bundle
                },
            },
            "proof_bundles": {
                str(bundle.get("persistence_key") or bundle.get("proof_bundle_id") or "bundle"): bundle
            },
        },
        claim_id=str(bundle.get("proof_bundle_id") or ""),
        exported_at=exported_at,
    )
    theorem_export["theorem_export_metadata"] = theorem_export_metadata
    theorem_export["proof_bundle_id"] = str(bundle.get("proof_bundle_id") or "")
    theorem_export["proof_bundle_digest"] = str(bundle.get("bundle_digest") or "")
    theorem_export["tdfol_formula_certainties"] = deepcopy(theorem_exports.get("tdfol_formula_certainties") or {})
    theorem_export["dcec_formula_certainties"] = deepcopy(theorem_exports.get("dcec_formula_certainties") or {})
    return theorem_export




# ---------------------------------------------------------------------------
# Complaint-type predicate templates
#
# Each template maps a claim element to:
#   - fol_template: First-Order Logic formula template (use {subject}/{object} placeholders)
#   - dcec_template: DCEC formula template
#   - predicate_types: list of expected predicate types for the element
#   - grounded_facts: example grounded predicate strings for the element
# ---------------------------------------------------------------------------

_COMPLAINT_PREDICATE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "employment_discrimination": {
        "label": "Employment Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "element_text": "Protected trait or class",
                "fol_template": "exists x (Employee(x) & HasProtectedTrait(x, {trait}) & MemberOf(x, ProtectedClass))",
                "dcec_template": "Believes(Claimant, HasProtectedTrait(Employee, {trait}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Employee(complainant) & HasProtectedTrait(complainant, race)",
                    "Employee(complainant) & HasProtectedTrait(complainant, disability)",
                ],
                "expected_supporting_evidence": ["personnel_record", "testimony", "hire_record"],
            },
            {
                "element_id": "employment_relationship",
                "element_text": "Employment relationship or workplace context",
                "fol_template": "exists x y (Employee(x) & Employer(y) & EmployedBy(x, y) & At(x, Workplace))",
                "dcec_template": "Knows(Employer, EmployedBy(Employee, Employer))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "EmployedBy(complainant, respondent)",
                    "WorkplaceContext(complainant, respondent, {start_date})",
                ],
                "expected_supporting_evidence": ["offer_letter", "pay_stub", "org_chart"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Adverse employment action or harassment",
                "fol_template": (
                    "exists x y (Employee(x) & Employer(y) & "
                    "AdverseAction(y, x, {action_type}) & OccurredAt({action_type}, {date}))"
                ),
                "dcec_template": "Happens(AdverseAction(Employer, Employee, {action_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "AdverseAction(respondent, complainant, termination)",
                    "AdverseAction(respondent, complainant, demotion)",
                ],
                "expected_supporting_evidence": ["termination_notice", "discipline_record", "performance_review"],
            },
            {
                "element_id": "discriminatory_motive",
                "element_text": "Facts suggesting discriminatory motive",
                "fol_template": (
                    "exists x y t (AdverseAction(y, x, {action_type}) & "
                    "HasProtectedTrait(x, {trait}) & "
                    "CausedBy({action_type}, HasProtectedTrait(x, {trait})))"
                ),
                "dcec_template": (
                    "Causes(HasProtectedTrait(Employee, {trait}), AdverseAction(Employer, Employee, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(termination, HasProtectedTrait(complainant, race))",
                    "DiscriminatoryMotive(respondent, complainant, disability)",
                ],
                "expected_supporting_evidence": ["email", "witness_statement", "comparator_record"],
            },
        ],
    },
    "housing_discrimination": {
        "label": "Housing Discrimination",
        "elements": [
            {
                "element_id": "protected_trait",
                "element_text": "Protected trait or class",
                "fol_template": "exists x (Tenant(x) & HasProtectedTrait(x, {trait}) & MemberOf(x, ProtectedClass))",
                "dcec_template": "Believes(Claimant, HasProtectedTrait(Tenant, {trait}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Tenant(complainant) & HasProtectedTrait(complainant, race)",
                    "Tenant(complainant) & HasProtectedTrait(complainant, disability)",
                ],
                "expected_supporting_evidence": ["application_record", "testimony"],
            },
            {
                "element_id": "housing_context",
                "element_text": "Housing relationship or tenancy context",
                "fol_template": (
                    "exists x y (Tenant(x) & Landlord(y) & "
                    "HasHousingRelationship(x, y, {relationship_type}))"
                ),
                "dcec_template": "Knows(Landlord, HasHousingRelationship(Tenant, Landlord, {relationship_type}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "HasHousingRelationship(complainant, respondent, tenant)",
                    "HasHousingRelationship(complainant, respondent, applicant)",
                ],
                "expected_supporting_evidence": ["lease", "application_record", "rent_record"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Discriminatory housing action",
                "fol_template": (
                    "exists x y (Landlord(y) & Tenant(x) & "
                    "HousingAdverseAction(y, x, {action_type}) & OccurredAt({action_type}, {date}))"
                ),
                "dcec_template": "Happens(HousingAdverseAction(Landlord, Tenant, {action_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "HousingAdverseAction(respondent, complainant, eviction)",
                    "HousingAdverseAction(respondent, complainant, denial)",
                ],
                "expected_supporting_evidence": ["denial_notice", "eviction_notice", "witness_statement"],
            },
            {
                "element_id": "discriminatory_motive",
                "element_text": "Facts suggesting discriminatory motive",
                "fol_template": (
                    "exists x y (HousingAdverseAction(y, x, {action_type}) & "
                    "HasProtectedTrait(x, {trait}) & "
                    "CausedBy({action_type}, HasProtectedTrait(x, {trait})))"
                ),
                "dcec_template": (
                    "Causes(HasProtectedTrait(Tenant, {trait}), HousingAdverseAction(Landlord, Tenant, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(denial, HasProtectedTrait(complainant, race))",
                    "DiscriminatoryMotive(respondent, complainant, disability)",
                ],
                "expected_supporting_evidence": ["landlord_message", "witness_statement"],
            },
        ],
    },
    "retaliation": {
        "label": "Retaliation",
        "elements": [
            {
                "element_id": "protected_activity",
                "element_text": "Protected activity",
                "fol_template": (
                    "exists x (Employee(x) & ProtectedActivity(x, {activity_type}) & "
                    "OccurredAt({activity_type}, {date}))"
                ),
                "dcec_template": "Happens(ProtectedActivity(Employee, {activity_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "ProtectedActivity(complainant, discrimination_complaint)",
                    "ProtectedActivity(complainant, safety_report)",
                ],
                "expected_supporting_evidence": ["hr_complaint", "eeoc_filing", "email"],
            },
            {
                "element_id": "knowledge_of_activity",
                "element_text": "Employer knowledge of protected activity",
                "fol_template": (
                    "exists x y (Employee(x) & Employer(y) & "
                    "Knows(y, ProtectedActivity(x, {activity_type})))"
                ),
                "dcec_template": "Knows(Employer, ProtectedActivity(Employee, {activity_type}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Knows(respondent, ProtectedActivity(complainant, discrimination_complaint))",
                ],
                "expected_supporting_evidence": ["acknowledgment", "email", "witness_statement"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Adverse action following protected activity",
                "fol_template": (
                    "exists x y (Employee(x) & Employer(y) & "
                    "AdverseAction(y, x, {action_type}) & "
                    "After(AdverseAction(y, x, {action_type}), ProtectedActivity(x, {activity_type})))"
                ),
                "dcec_template": (
                    "Happens(AdverseAction(Employer, Employee, {action_type}), {date}) & "
                    "After({date}, {activity_date})"
                ),
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact", "temporal_relation"],
                "grounded_facts": [
                    "AdverseAction(respondent, complainant, termination)",
                    "After(termination_date, complaint_date)",
                ],
                "expected_supporting_evidence": ["termination_notice", "schedule_change", "witness_statement"],
            },
            {
                "element_id": "causal_connection",
                "element_text": "Causal connection between protected activity and adverse action",
                "fol_template": (
                    "exists x y (CausedBy(AdverseAction(y, x, {action_type}), ProtectedActivity(x, {activity_type})) & "
                    "TemporalProximity(AdverseAction(y, x, {action_type}), ProtectedActivity(x, {activity_type})))"
                ),
                "dcec_template": (
                    "Causes(ProtectedActivity(Employee, {activity_type}), AdverseAction(Employer, Employee, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(termination, discrimination_complaint)",
                    "TemporalProximity(termination_date, complaint_date)",
                ],
                "expected_supporting_evidence": ["email", "witness_statement", "timeline_record"],
            },
        ],
    },
    "fair_housing": {
        "label": "Fair Housing",
        "elements": [
            {
                "element_id": "protected_trait",
                "element_text": "Protected trait or class",
                "fol_template": "exists x (Person(x) & HasProtectedTrait(x, {trait}) & MemberOf(x, ProtectedClass))",
                "dcec_template": "Believes(Claimant, HasProtectedTrait(Person, {trait}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "Person(complainant) & HasProtectedTrait(complainant, race)",
                    "Person(complainant) & HasProtectedTrait(complainant, disability)",
                ],
                "expected_supporting_evidence": ["application_record", "testimony"],
            },
            {
                "element_id": "housing_activity",
                "element_text": "Covered housing activity",
                "fol_template": (
                    "exists x y (Person(x) & HousingProvider(y) & "
                    "HousingActivity(y, x, {activity_type}))"
                ),
                "dcec_template": "Knows(HousingProvider, HousingActivity(HousingProvider, Person, {activity_type}))",
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "HousingActivity(respondent, complainant, rental_application)",
                    "HousingActivity(respondent, complainant, loan_application)",
                ],
                "expected_supporting_evidence": ["application_record", "lease", "loan_document"],
            },
            {
                "element_id": "adverse_action",
                "element_text": "Discriminatory or adverse housing action",
                "fol_template": (
                    "exists x y (HousingProvider(y) & Person(x) & "
                    "AdverseHousingAction(y, x, {action_type}) & OccurredAt({action_type}, {date}))"
                ),
                "dcec_template": "Happens(AdverseHousingAction(HousingProvider, Person, {action_type}), {date})",
                "predicate_types": ["factual_statement", "claim_element", "temporal_fact"],
                "grounded_facts": [
                    "AdverseHousingAction(respondent, complainant, denial)",
                    "AdverseHousingAction(respondent, complainant, steering)",
                ],
                "expected_supporting_evidence": ["denial_notice", "correspondence", "witness_statement"],
            },
            {
                "element_id": "discriminatory_motive",
                "element_text": "Facts suggesting discriminatory motive",
                "fol_template": (
                    "exists x y (AdverseHousingAction(y, x, {action_type}) & "
                    "HasProtectedTrait(x, {trait}) & "
                    "CausedBy({action_type}, HasProtectedTrait(x, {trait})))"
                ),
                "dcec_template": (
                    "Causes(HasProtectedTrait(Person, {trait}), AdverseHousingAction(HousingProvider, Person, {action_type}))"
                ),
                "predicate_types": ["factual_statement", "claim_element"],
                "grounded_facts": [
                    "CausedBy(denial, HasProtectedTrait(complainant, race))",
                    "DiscriminatoryMotive(respondent, complainant, disability)",
                ],
                "expected_supporting_evidence": ["correspondence", "witness_statement", "comparator_record"],
            },
        ],
    },
}


def get_predicate_templates(complaint_type: str) -> Dict[str, Any]:
    """Return grounded predicate templates for *complaint_type*.

    Supports ``employment_discrimination``, ``housing_discrimination``,
    ``retaliation``, and ``fair_housing``.  Returns an empty elements list
    for unknown types.

    Each element in the result carries ``fol_template``, ``dcec_template``,
    ``predicate_types``, and ``grounded_facts`` ready for use in
    :func:`map_claim_elements_to_predicates`.
    """
    normalized_type = str(complaint_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    template = _COMPLAINT_PREDICATE_TEMPLATES.get(normalized_type)
    if template is None:
        return with_adapter_metadata(
            {
                "status": "not_found",
                "complaint_type": complaint_type,
                "label": "",
                "elements": [],
                "element_count": 0,
                "supported_complaint_types": list(_COMPLAINT_PREDICATE_TEMPLATES.keys()),
            },
            operation="get_predicate_templates",
            backend_available=True,
            implementation_status="implemented",
        )
    return with_adapter_metadata(
        {
            "status": "success",
            "complaint_type": complaint_type,
            "label": template.get("label", ""),
            "elements": template["elements"],
            "element_count": len(template["elements"]),
            "supported_complaint_types": list(_COMPLAINT_PREDICATE_TEMPLATES.keys()),
        },
        operation="get_predicate_templates",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={"complaint_type": complaint_type},
    )


def map_claim_elements_to_predicates(
    claim_type: str,
    elements: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Map claim *elements* to FOL/DCEC predicates using the template for *claim_type*.

    Each input element should be a dict with at least ``element_id`` or
    ``element_text``.  The function enriches each element with its matching
    template (``fol_template``, ``dcec_template``) and produces a
    ``predicates`` list ready for :func:`prove_claim_elements`.

    Returns a structured payload with ``predicates`` (list of predicate dicts)
    and ``template_match_count`` (how many elements matched a template entry).
    """
    templates_result = get_predicate_templates(claim_type)
    element_templates = {
        t["element_id"]: t
        for t in (templates_result.get("elements") or [])
        if isinstance(t, dict) and t.get("element_id")
    }

    predicates: List[Dict[str, Any]] = []
    template_match_count = 0
    unmapped_element_ids: List[str] = []
    all_support_facts: List[Dict[str, Any]] = []

    for element in list(elements):
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or element.get("label") or "")
        coverage_status = str(element.get("status") or element.get("coverage_status") or "missing")
        predicate_id = element.get("predicate_id") or f"{claim_type}:{element_id}" if element_id else f"{claim_type}:unknown"
        support_facts = [
            dict(fact)
            for fact in element.get("support_facts", []) or []
            if isinstance(fact, dict)
        ]
        all_support_facts.extend(support_facts)
        fact_registry_summary = (
            dict(element.get("fact_registry_summary"))
            if isinstance(element.get("fact_registry_summary"), dict)
            else dict(element.get("support_fact_registry_summary"))
            if isinstance(element.get("support_fact_registry_summary"), dict)
            else _summarize_fact_registry_for_facts(support_facts)
        )

        tmpl = element_templates.get(element_id)
        if tmpl:
            template_match_count += 1
            fol_template = tmpl.get("fol_template", "")
            dcec_template = tmpl.get("dcec_template", "")
        else:
            fol_template = ""
            dcec_template = ""
            if element_id:
                unmapped_element_ids.append(element_id)

        predicate: Dict[str, Any] = {
            "predicate_type": "claim_element",
            "claim_type": claim_type,
            "predicate_id": predicate_id,
            "claim_element_id": element_id,
            "claim_element_text": element_text,
            "coverage_status": coverage_status,
            "formula": fol_template,
            "fol_template": fol_template,
            "dcec_template": dcec_template,
            "grounded_facts": tmpl.get("grounded_facts", []) if tmpl else [],
            "expected_predicate_types": tmpl.get("predicate_types", ["claim_element"]) if tmpl else ["claim_element"],
            "template_matched": bool(tmpl),
            "support_facts": support_facts,
            "fact_registry_summary": fact_registry_summary,
        }
        predicates.append(predicate)

    fact_registry_summary = _summarize_fact_registry_for_facts(all_support_facts)
    return with_adapter_metadata(
        {
            "status": "success",
            "claim_type": claim_type,
            "predicates": predicates,
            "predicate_count": len(predicates),
            "template_match_count": template_match_count,
            "unmapped_element_ids": unmapped_element_ids,
            "fact_registry_summary": fact_registry_summary,
        },
        operation="map_claim_elements_to_predicates",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={
            "claim_type": claim_type,
            "element_count": len(predicates),
            "fact_registry_summary": fact_registry_summary,
        },
    )


# ---------------------------------------------------------------------------
# Source-bound legal rule candidates (CIMP-LAW-04)
# ---------------------------------------------------------------------------

SOURCE_BOUND_RULE_CONTRACT = "source-bound-legal-rule/v1"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RULE_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+)?", re.MULTILINE)
_EXCEPTION_RE = re.compile(
    r"\b(except(?:\s+(?:that|when|where|if))?|unless|provided that|however)\b",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"^(if|when|where|whenever)\s+(.+?),\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_AND_RE = re.compile(r"\band\b", re.IGNORECASE)
_OR_RE = re.compile(r"\bor\b", re.IGNORECASE)
_PROCEDURAL_RE = re.compile(
    r"\b(within\s+\d+\s+(?:days|hours|months)|deadline|timely|exhaust|notice|"
    r"venue|filed|file[sd]?|procedure|service of process|statute of limitations)\b",
    re.IGNORECASE,
)
_DEONTIC_RULES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("prohibition", re.compile(
        r"\b(must not|shall not|may not|cannot|can not|is prohibited|is forbidden|prohibited)\b",
        re.IGNORECASE,
    )),
    ("obligation", re.compile(
        r"\b(must|shall|required to|is required to|has a duty to|ought to)\b",
        re.IGNORECASE,
    )),
    ("permission", re.compile(
        r"\b(may|is permitted to|is allowed to|is entitled to|has the right to)\b",
        re.IGNORECASE,
    )),
)
_UNKNOWN_TOKENS = frozenset({
    "", "unknown", "unspecified", "n/a", "na", "none", "null", "current", "latest", "unverified",
})
_LEGACY_DISCRIMINATION_TEMPLATES: Tuple[Tuple[str, str], ...] = (
    ("Protected Class Membership", "Plaintiff must be member of protected class"),
    ("Adverse Action", "Plaintiff suffered adverse employment/housing action"),
    ("Causal Connection", "Protected class status was motivating factor"),
)
def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_context(authority: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key in ("metadata", "provenance", "applicable_date", "date_context"):
        nested = authority.get(key)
        if isinstance(nested, Mapping):
            merged.update(dict(nested))
    merged.update(dict(authority))
    return merged


def _normalize_sha256(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1].strip()
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    return ""


def sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _byte_span(source_text: str, char_start: int, char_end: int) -> Tuple[int, int]:
    prefix = source_text[:char_start].encode("utf-8")
    fragment = source_text[char_start:char_end].encode("utf-8")
    return len(prefix), len(prefix) + len(fragment)


def _unique_fragment_span(source_text: str, fragment: str) -> Tuple[Optional[Dict[str, Any]], str]:
    if not source_text or not fragment:
        return None, "missing_source_span"
    start = source_text.find(fragment)
    if start < 0:
        return None, "missing_source_span"
    if source_text.find(fragment, start + 1) != -1:
        return None, "ambiguous_source_span"
    byte_start, byte_end = _byte_span(source_text, start, start + len(fragment))
    sliced = source_text.encode("utf-8")[byte_start:byte_end].decode("utf-8")
    if sliced != fragment:
        return None, "source_span_mismatch"
    return {
        "start": byte_start,
        "end": byte_end,
        "text": fragment,
        "unit": "utf-8-bytes",
    }, ""


def _iter_rule_sentences(source_text: str) -> List[Tuple[str, int, int]]:
    found: List[Tuple[str, int, int]] = []
    for match in _RULE_SENTENCE_RE.finditer(source_text):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        leading = len(raw) - len(raw.lstrip())
        char_start = match.start() + leading
        char_end = char_start + len(stripped)
        if source_text[char_start:char_end] != stripped:
            continue
        found.append((stripped, char_start, char_end))
    return found


def _deontic_operator(sentence: str) -> str:
    for name, pattern in _DEONTIC_RULES:
        if pattern.search(sentence):
            return name
    return "unknown"


def _clause_record(source_text: str, fragment: str) -> Dict[str, Any]:
    span, status = _unique_fragment_span(source_text, fragment.strip(" ,;"))
    return {
        "text": fragment.strip(" ,;"),
        "span": span,
        "span_status": "exact" if span else status,
    }


def _structure_for_sentence(source_text: str, sentence: str) -> Dict[str, Any]:
    operative = sentence
    exceptions: List[Dict[str, Any]] = []
    exception_match = _EXCEPTION_RE.search(sentence)
    if exception_match:
        exception_text = sentence[exception_match.start():].strip()
        operative = sentence[:exception_match.start()].strip(" ,;")
        exceptions.append(_clause_record(source_text, exception_text))
    conditions: List[Dict[str, Any]] = []
    condition_match = _CONDITION_RE.match(operative)
    if condition_match:
        conditions.append(_clause_record(source_text, condition_match.group(2).strip()))
        operative_for_connective = condition_match.group(3).strip()
    else:
        operative_for_connective = operative
    conjunction_count = len(_AND_RE.findall(operative_for_connective))
    disjunction_count = len(_OR_RE.findall(operative_for_connective))
    if conjunction_count and disjunction_count:
        connective = "ambiguous"
    elif conjunction_count:
        connective = "conjunction"
    elif disjunction_count:
        connective = "disjunction"
    else:
        connective = "none"
    conjuncts: List[Dict[str, Any]] = []
    disjuncts: List[Dict[str, Any]] = []
    if connective == "conjunction":
        conjuncts = [_clause_record(source_text, part) for part in _AND_RE.split(operative_for_connective) if part.strip()]
    elif connective == "disjunction":
        disjuncts = [_clause_record(source_text, part) for part in _OR_RE.split(operative_for_connective) if part.strip()]
    deontic = _deontic_operator(sentence)
    clause_parts = [operative_for_connective] + [item["text"] for item in exceptions if item.get("text")]
    if conditions:
        clause_parts.append(conditions[0]["text"])
    procedural_parts = [part for part in clause_parts if part and _PROCEDURAL_RE.search(part)]
    substantive_parts = [
        part for part in clause_parts
        if part and not _PROCEDURAL_RE.search(part) and _deontic_operator(part) != "unknown"
    ]
    if procedural_parts and substantive_parts:
        rule_character = "mixed"
    elif procedural_parts or _PROCEDURAL_RE.search(sentence):
        rule_character = "procedural"
    elif deontic != "unknown":
        rule_character = "substantive"
    else:
        rule_character = "unknown"
    return {
        "conditions": conditions,
        "exceptions": exceptions,
        "connective": connective,
        "conjunction_count": conjunction_count,
        "disjunction_count": disjunction_count,
        "conjuncts": conjuncts,
        "disjuncts": disjuncts,
        "rule_character": rule_character,
        "deontic_operator": deontic,
        "deontic_operator_source": "pattern_heuristic",
        "deontic_operator_is_proof": False,
        "entailment_status": "unsupported",
    }


def _iso_date(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 64:
        return ""
    text = value.strip()
    if not _ISO_DATE_RE.fullmatch(text):
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _authority_coordinates(authority: Mapping[str, Any]) -> Dict[str, Any]:
    context = _nested_context(authority)
    jurisdiction = _first_text(context, "jurisdiction")
    authority_id = _first_text(context, "authority_id", "authority_identity", "id")
    citation = _first_text(context, "citation", "cite")
    version = _first_text(context, "authority_version", "version", "corpus_version", "release")
    source_text = authority.get("source_text")
    if not isinstance(source_text, str) or source_text == "":
        source_text = authority.get("text") if isinstance(authority.get("text"), str) else ""
    supplied_hash = _normalize_sha256(
        context.get("source_hash") or context.get("content_hash") or context.get("authority_hash")
    )
    hash_scope = str(context.get("content_hash_scope") or context.get("source_hash_scope") or "").strip()
    dates = {
        "effective_date": _iso_date(context.get("effective_date")),
        "as_of_date": _iso_date(context.get("as_of_date") or context.get("applicable_date") or context.get("applicable_on")),
        "expiration_date": _iso_date(context.get("expiration_date")),
    }
    return {
        "jurisdiction": jurisdiction,
        "authority_id": authority_id,
        "citation": citation,
        "authority_version": version,
        "source_text": source_text,
        "source_hash": supplied_hash,
        "hash_scope": hash_scope,
        "applicable_date": dates,
    }


def _known_token(value: str) -> bool:
    return value.strip().lower() not in _UNKNOWN_TOKENS


_TEMPORAL_AUTHORITY_MODULE = (
    "ipfs_datasets_py.logic.integration.reasoning.legal_ir_temporal_authority"
)
_TEMPORAL_APPLICABILITY_CONTRACT = "legal_ir_temporal_applicability_v1"
_BLOCKING_TREATMENT_TYPES = frozenset({
    "adverse",
    "good_law_unconfirmed",
    "questioned",
    "limits",
    "distinguishes",
    "superseded",
})
_TEMPORAL_STATUS_LABELS = {
    "applicable": "effective",
    "not_yet_effective": "future",
    "expired": "expired",
    "repealed": "repealed",
    "superseded": "superseded",
    "wrong_jurisdiction": "wrong_jurisdiction",
    "authority_preempted": "authority_preempted",
    "emergency_expired": "expired",
    "unresolved_authority": "unavailable",
}


_TEMPORAL_MAX_VERSIONS = 64
_TEMPORAL_MAX_CHANGES = 128
_TEMPORAL_MAX_TEXT = 65536
_TEMPORAL_MAX_RULES = 256


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


def _date_aliases(mapping: Mapping[str, Any], keys: Sequence[str]) -> Tuple[str, str]:
    present = [mapping[key] for key in keys if mapping.get(key) not in (None, "")
               and not (key == "applicable_date" and isinstance(mapping[key], Mapping))]
    parsed = [_iso_date(value) if isinstance(value, str) else "" for value in present]
    if any(not value for value in parsed):
        return "", "invalid_source_date"
    if len(set(parsed)) > 1:
        return "", "contradictory_date_context"
    return (parsed[0] if parsed else ""), ""


def _source_date_aliases(payload: Mapping[str, Any], keys: Sequence[str]) -> Tuple[str, str]:
    values = []
    for container in (payload, *(payload.get(key) for key in
                       ("metadata", "provenance", "applicable_date", "date_context", "temporal_window"))):
        if isinstance(container, Mapping):
            value, reason = _date_aliases(container, keys)
            if reason:
                return "", reason
            if value:
                values.append(value)
    if len(set(values)) > 1:
        return "", "contradictory_date_context"
    return (values[0] if values else ""), ""


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


def _iter_treatment_records(authority: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    edges = authority.get("authority_treatment_edges")
    if isinstance(edges, list) and edges:
        records.extend(item for item in edges if isinstance(item, Mapping))
    else:
        raw = authority.get("treatment_records")
        if not isinstance(raw, list):
            summary = authority.get("treatment_summary")
            raw = summary.get("records") if isinstance(summary, Mapping) else []
        if isinstance(raw, list):
            records.extend(item for item in raw if isinstance(item, Mapping))
    return records


def requirement_treatment_support(authority: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep treatment edges visible and say whether they block requirement support."""
    visible: List[Dict[str, Any]] = []
    types: List[str] = []
    for record in _iter_treatment_records(authority):
        treatment_type = str(
            record.get("relation_type") or record.get("treatment_type") or record.get("type") or ""
        ).strip()
        if not treatment_type:
            continue
        types.append(treatment_type)
        visible.append({
            "treatment_type": treatment_type,
            "source_authority_id": str(
                record.get("source_authority_id") or record.get("treated_by_authority_id") or ""
            ),
            "target_authority_id": str(
                record.get("target_authority_id")
                or record.get("treated_authority_id")
                or record.get("target_id")
                or ""
            ),
            "explanation": str(record.get("explanation") or record.get("treatment_explanation") or ""),
        })
    blocking = [name for name in types if name in _BLOCKING_TREATMENT_TYPES]
    return {
        "treatment_edges": visible,
        "treatment_types": list(dict.fromkeys(types)),
        "treatment_edges_visible": True,
        "blocking_treatments": list(dict.fromkeys(blocking)),
        "treatment_blocks_support": bool(blocking),
        "support_eligible": not blocking,
    }


def _selected_law_versions(authority: Mapping[str, Any], coordinates: Mapping[str, Any]) -> List[Dict[str, Any]]:
    supplied = authority.get("law_versions")
    if isinstance(supplied, list) and supplied:
        versions = [dict(item) for item in supplied if isinstance(item, Mapping)]
        if versions:
            return versions
    dates = coordinates.get("applicable_date") if isinstance(coordinates.get("applicable_date"), Mapping) else {}
    version = str(coordinates.get("authority_version") or "")
    authority_id = str(coordinates.get("authority_id") or coordinates.get("citation") or "authority")
    window = authority.get("temporal_window") if isinstance(authority.get("temporal_window"), Mapping) else {}
    return [{
        "law_version_id": str(authority.get("law_version_id") or f"{authority_id}:{version or 'unspecified'}"),
        "citation": str(coordinates.get("citation") or ""),
        "authority_id": str(coordinates.get("authority_id") or ""),
        "jurisdiction": str(coordinates.get("jurisdiction") or ""),
        "version": version,
        "effective_date": str(window.get("effective_date") or dates.get("effective_date") or ""),
        "sunset_date": str(window.get("sunset_date") or authority.get("sunset_date") or authority.get("expiration_date") or dates.get("expiration_date") or ""),
        "repeal_date": str(window.get("repeal_date") or authority.get("repeal_date") or ""),
        "superseded_date": str(window.get("superseded_date") or authority.get("superseded_date") or ""),
    }]


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


def is_applicable_legal_requirement(attributes: Any) -> bool:
    """Return whether a graph element may be used as an applicable requirement.

    Records that never went through this gate stay eligible so existing
    hand-built elements keep their previous meaning. Explicit templates,
    unpromoted candidates, unavailable temporal decisions, and blocking
    treatment marks do not.
    """
    if not isinstance(attributes, Mapping):
        return False
    if attributes.get("legacy_template") is True:
        return False
    if attributes.get("verification_status") == "unverified_template":
        return False
    if attributes.get("applicable") is False:
        return False
    if attributes.get("promotion_status") in {"candidate", "unverified_template", "not_promoted"}:
        return False
    if attributes.get("support_eligible") is False or attributes.get("treatment_blocks_support") is True:
        return False
    temporal = attributes.get("temporal_applicability")
    if isinstance(temporal, Mapping):
        if temporal.get("applicable") is False:
            return False
        if str(temporal.get("applicability_status") or "") not in {"", "effective", "applicable"}:
            return False
    return True


def _promotion_reasons(
    *,
    coordinates: Mapping[str, Any],
    span: Optional[Mapping[str, Any]],
    span_status: str,
    structure: Mapping[str, Any],
    legacy_template: bool,
) -> List[str]:
    reasons: List[str] = []
    if legacy_template:
        reasons.append("legacy_unverified_template")
    if not _known_token(str(coordinates.get("jurisdiction") or "")):
        reasons.append("missing_jurisdiction")
    if not (_known_token(str(coordinates.get("authority_id") or "")) or _known_token(str(coordinates.get("citation") or ""))):
        reasons.append("missing_authority_identity")
    if not _known_token(str(coordinates.get("authority_version") or "")):
        reasons.append("missing_authority_version")
    source_text = str(coordinates.get("source_text") or "")
    supplied_hash = str(coordinates.get("source_hash") or "")
    if not source_text:
        reasons.append("missing_source_text")
    if not supplied_hash:
        reasons.append("missing_source_hash")
    elif source_text:
        full_hash = sha256_utf8(source_text)
        span_hash = sha256_utf8(str(span.get("text") or "")) if span else ""
        scope = str(coordinates.get("hash_scope") or "")
        matches_full = supplied_hash == full_hash
        matches_span = scope == "source_passage" and bool(span_hash) and supplied_hash == span_hash
        if not matches_full and not matches_span:
            reasons.append("source_hash_mismatch")
    if span is None:
        reasons.append(span_status or "missing_source_span")
    dates = coordinates.get("applicable_date") if isinstance(coordinates.get("applicable_date"), Mapping) else {}
    if not (dates.get("effective_date") or dates.get("as_of_date")):
        reasons.append("missing_applicable_date")
    if structure.get("deontic_operator") == "unknown":
        reasons.append("unsupported_deontic_extraction")
    if structure.get("connective") == "ambiguous":
        reasons.append("ambiguous_connective")
    if structure.get("rule_character") == "unknown":
        reasons.append("ambiguous_rule_character")
    for clause in list(structure.get("conditions") or []) + list(structure.get("exceptions") or []):
        if isinstance(clause, Mapping) and clause.get("span_status") == "ambiguous_source_span":
            reasons.append("ambiguous_clause_span")
            break
    # Caller-supplied promotion flags are never a reason to pass.
    return list(dict.fromkeys(reasons))


def _candidate_record(
    *,
    authority: Mapping[str, Any],
    coordinates: Mapping[str, Any],
    sentence: str,
    span: Optional[Dict[str, Any]],
    span_status: str,
    structure: Mapping[str, Any],
    legacy_template: bool,
    temporal: Optional[Dict[str, Any]] = None,
    treatment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reasons = _promotion_reasons(
        coordinates=coordinates,
        span=span,
        span_status=span_status,
        structure=structure,
        legacy_template=legacy_template,
    )
    temporal = evaluate_temporal_requirement_applicability(authority) if temporal is None else deepcopy(temporal)
    treatment = requirement_treatment_support(authority) if treatment is None else deepcopy(treatment)
    if not temporal.get("applicable"):
        reason = str(temporal.get("review_reason") or "temporal_applicability_unavailable")
        reasons.append(reason)
    promoted = not reasons
    support_eligible = bool(promoted and treatment.get("support_eligible") and temporal.get("applicable"))
    source_text = str(coordinates.get("source_text") or "")
    span_text = str(span.get("text") if span else "")
    return {
        "contract": SOURCE_BOUND_RULE_CONTRACT,
        "status": "promoted" if promoted else "candidate",
        "promotion_status": "promoted" if promoted else "candidate",
        "verification_status": "promoted" if promoted else "candidate",
        "promoted": promoted,
        "applicable": promoted and support_eligible,
        "support_eligible": support_eligible,
        "treatment_blocks_support": bool(treatment.get("treatment_blocks_support")),
        "treatment_edges": list(treatment.get("treatment_edges") or []),
        "blocking_treatments": list(treatment.get("blocking_treatments") or []),
        "temporal_applicability": temporal,
        "legacy_template": legacy_template,
        "review_reason": ";".join(reasons),
        "review_reasons": reasons,
        "rule_text": sentence,
        "source_span": dict(span) if span else {"start": None, "end": None, "text": "", "unit": "utf-8-bytes"},
        "span_status": "exact" if span else span_status,
        "source_hash": str(coordinates.get("source_hash") or ""),
        "source_hash_scope": (
            "source_passage"
            if str(coordinates.get("hash_scope") or "") == "source_passage"
            else "authority_text"
        ),
        "authority_text_sha256": sha256_utf8(source_text) if source_text else "",
        "span_sha256": sha256_utf8(span_text) if span_text else "",
        "jurisdiction": str(coordinates.get("jurisdiction") or ""),
        "authority_id": str(coordinates.get("authority_id") or ""),
        "authority_identity": str(coordinates.get("authority_id") or coordinates.get("citation") or ""),
        "authority_version": str(coordinates.get("authority_version") or ""),
        "citation": str(coordinates.get("citation") or ""),
        "applicable_date": dict(coordinates.get("applicable_date") or {}),
        "structure": dict(structure),
        "rule_character": structure.get("rule_character", "unknown"),
        "deontic_operator": structure.get("deontic_operator", "unknown"),
        "deontic_operator_is_proof": False,
        "entailment_status": "unsupported",
        "about_complainant": False,
    }


def _unavailable_rule_candidates(reason: str) -> Dict[str, Any]:
    candidate = _candidate_record(
        authority={}, coordinates=_authority_coordinates({}), sentence="", span=None,
        span_status="missing_source_text", structure=_structure_for_sentence("", ""), legacy_template=False,
        temporal=_unavailable_temporal_applicability(reason),
        treatment={"support_eligible": False, "treatment_edges": [], "blocking_treatments": []})
    return {"contract": SOURCE_BOUND_RULE_CONTRACT, "candidates": [candidate],
            "promoted_requirements": [], "candidate_count": 1, "promoted_count": 0}


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


def legacy_unverified_requirement_templates(claim_types: Sequence[str]) -> List[Dict[str, Any]]:
    """Return simplified claim-keyword templates that cannot be applied as law."""
    claim_text = " ".join(str(item) for item in claim_types).lower()
    if "discrimination" not in claim_text:
        return []
    templates: List[Dict[str, Any]] = []
    for name, description in _LEGACY_DISCRIMINATION_TEMPLATES:
        templates.append({
            "name": name,
            "description": description,
            "required": True,
            "element_type": "legal_requirement",
            "verification_status": "unverified_template",
            "promotion_status": "unverified_template",
            "applicable": False,
            "legacy_template": True,
            "template_kind": "claim_keyword_template",
            "review_reason": "legacy_unverified_template",
            "source_bound": False,
            "about_complainant": False,
        })
    return templates


def _canonical_symbol(module: Any, name: str) -> Any:
    if module is None:
        return None
    return getattr(module, name, None)


def _canonical_modules_ready() -> bool:
    required = (
        _canonical_symbol(_canonical_pipeline_module, "compile_canonical_pipeline"),
        _canonical_symbol(_canonical_contracts_module, "CompilerRequest"),
        _canonical_symbol(_canonical_contracts_module, "CanonicalAtomVocabulary"),
        _canonical_symbol(_canonical_compiler_module, "TYPED_DEONTIC_COMPILER_CONFIG_CID"),
        _canonical_symbol(_canonical_source_map_module, "LegalIRSourceMapBuilder"),
        _canonical_symbol(_canonical_source_map_module, "build_legal_ir_source_map"),
        _canonical_symbol(_canonical_source_map_module, "validate_legal_ir_source_map"),
        _canonical_symbol(_canonical_source_map_module, "trace_legal_ir_fact"),
        _canonical_symbol(_canonical_source_map_module, "bind_legal_ir_artifact_source_map"),
    )
    return all(symbol is not None for symbol in required)


def _canonical_import_reason() -> str:
    return _provider_diagnostic(
        _canonical_pipeline_error
        or _canonical_contracts_error
        or _canonical_compiler_error
        or _canonical_source_map_error,
        fallback="Canonical compiler pipeline or source-map module is unavailable.",
    )


def canonical_compiler_identities() -> Dict[str, Any] | None:
    """Return live schema, compiler, policy, pipeline, and stage identities."""

    if not _canonical_modules_ready():
        return None
    contracts = _canonical_contracts_module
    compiler = _canonical_compiler_module
    pipeline = _canonical_pipeline_module
    source_maps = _canonical_source_map_module
    stage_table = tuple(pipeline.compiler_stage_identities())
    return {
        "source_map_schema": str(source_maps.LEGAL_IR_SOURCE_MAP_SCHEMA_VERSION),
        "compiler_interface": str(contracts.CANONICAL_STRUCTURED_TEXT_COMPILER_INTERFACE),
        "compiler_config_cid": str(compiler.TYPED_DEONTIC_COMPILER_CONFIG_CID),
        "policy_cid": str(contracts.CANONICAL_PARITY_POLICY_CID),
        "pipeline_interface": str(pipeline.CANONICAL_COMPILER_PIPELINE_INTERFACE),
        "pipeline_cid": str(pipeline.CANONICAL_COMPILER_PIPELINE_CID),
        "stage_ids": [str(item["stage_id"]) for item in stage_table],
        "stage_interfaces": {
            str(item["stage_id"]): str(item["interface"]) for item in stage_table
        },
    }


def _canonical_evidence(
    *,
    executed: bool = False,
    status: str = "",
    traceable: bool = False,
    source_map_valid: bool = False,
    schema_match: bool = True,
    tampered: bool = False,
    reason: str = "",
) -> Dict[str, Any]:
    return {
        "module_present": _canonical_modules_ready(),
        "provider": "ipfs_datasets_py",
        "module_path": "ipfs_datasets_py.logic.integration.reasoning.legal_ir_canonical_pipeline",
        "executed": executed,
        "status": status,
        "traceable": traceable,
        "source_map_valid": source_map_valid,
        "schema_match": schema_match,
        "tampered": tampered,
        "reason": reason,
        "identities": canonical_compiler_identities() or {},
    }


def get_canonical_compiler_capability() -> CanonicalCompilerCapability:
    """Return the canonical compiler gate.

    Importing the pipeline module leaves the capability degraded. Implemented
    status is recorded only after a supported compile with a validated source
    map, and only while the live identities still match that execution.
    """

    if not _canonical_modules_ready():
        return classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
    execution = _CANONICAL_SUPPORTED_EXECUTION
    live = canonical_compiler_identities() or {}
    if not execution:
        return classify_canonical_compiler_capability(_canonical_evidence())
    if execution.get("identities") != live:
        return classify_canonical_compiler_capability(
            _canonical_evidence(
                schema_match=False,
                reason="Live canonical identities no longer match the executed formalization.",
            )
        )
    return classify_canonical_compiler_capability(
        _canonical_evidence(
            executed=True,
            status="success",
            traceable=True,
            source_map_valid=True,
        )
    )


def reset_canonical_formalization_cache() -> None:
    """Drop cached formalizations and the supported-execution marker.

    Receipts already returned to callers are independent copies. This reset
    clears only the adapter's reuse index.
    """

    global _CANONICAL_SUPPORTED_EXECUTION
    _CANONICAL_FORMALIZATION_RECEIPTS.clear()
    _CANONICAL_FORMALIZATION_CACHE.clear()
    _CANONICAL_SUPPORTED_EXECUTION = None


def inspect_canonical_formalization_receipt(receipt_id: str) -> Dict[str, Any] | None:
    """Return a stored formalization receipt without treating it as reusable."""

    stored = _CANONICAL_FORMALIZATION_RECEIPTS.get(str(receipt_id or ""))
    if stored is None:
        return None
    return deepcopy(stored)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _jsonable(to_dict())
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _identity_mismatch(live: Mapping[str, Any], expected: Mapping[str, Any]) -> List[str]:
    mismatched: List[str] = []
    for key, expected_value in expected.items():
        if expected_value is None:
            continue
        actual = live.get(key)
        if key == "stage_ids":
            actual_ids = tuple(actual or ())
            expected_ids = tuple(expected_value)
            if actual_ids != expected_ids:
                mismatched.append(key)
            continue
        if str(actual or "") != str(expected_value):
            mismatched.append(key)
    return mismatched


def _vocabulary_from_mapping(value: Mapping[str, Any]) -> Any:
    vocabulary_type = _canonical_contracts_module.CanonicalAtomVocabulary
    return vocabulary_type(
        actors=tuple(value.get("actors") or ()),
        actions=tuple(value.get("actions") or ()),
        objects=tuple(value.get("objects") or ()),
        qualifiers=tuple(value.get("qualifiers") or ()),
    )


def _legal_source_text(
    source_text: str,
    legal_context: Mapping[str, Any] | None,
) -> tuple[str, str]:
    context = legal_context if isinstance(legal_context, Mapping) else {}
    versioned = str(
        context.get("source_text")
        or context.get("normalized_text")
        or ""
    ).strip()
    if versioned:
        return versioned, "legal_context"
    return str(source_text or ""), "argument"


def _citation_from_context(legal_context: Mapping[str, Any] | None, request_id: str) -> str:
    context = legal_context if isinstance(legal_context, Mapping) else {}
    for key in ("citation", "authority_locator", "source_locator", "authority_id"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return request_id or "synthetic-legal-source"


def _version_from_context(legal_context: Mapping[str, Any] | None) -> str:
    context = legal_context if isinstance(legal_context, Mapping) else {}
    for key in ("authority_version", "corpus_version", "version"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return ""


def _compile_cache_key(
    identities: Mapping[str, Any],
    *,
    source_cid: str,
    request_id: str,
    vocabulary: Mapping[str, Any],
    allow_explicit_partial: bool,
    authority_version: str,
) -> str:
    payload = {
        "allow_explicit_partial": allow_explicit_partial,
        "authority_version": authority_version,
        "identities": dict(identities),
        "request_id": request_id,
        "source_cid": source_cid,
        "vocabulary": dict(vocabulary),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _source_cid_for_text(source_text: str) -> str:
    cid_for_bytes = _canonical_symbol(_canonical_contracts_module, "cid_for_bytes")
    if cid_for_bytes is None:
        from ipfs_datasets_py.utils.cid_utils import cid_for_bytes as cid_for_bytes  # type: ignore
    return str(cid_for_bytes(source_text.encode("utf-8")))


def _prevalidate_character_spans(
    source_text: str,
    source_cid: str,
    entries: Sequence[Any],
) -> List[Dict[str, str]]:
    """Reject spans before the source-map builder can clamp them.

    Canonical entries are character offsets. Byte offsets from other contracts
    are not accepted, including offsets that would become in-range after clamping.
    """

    issues: List[Dict[str, str]] = []
    character_length = len(source_text)
    if not entries:
        issues.append(
            {
                "code": "empty_source_map",
                "message": "Canonical result emitted no source-map entries.",
                "field_path": "source_map",
            }
        )
        return issues
    for index, entry in enumerate(entries):
        path = f"source_map[{index}]"
        entry_cid = str(getattr(entry, "source_cid", "") or "")
        if entry_cid != source_cid:
            issues.append(
                {
                    "code": "source_cid_mismatch",
                    "message": "Source-map entry CID does not match the legal source text.",
                    "field_path": path,
                }
            )
        start = getattr(entry, "start", None)
        end = getattr(entry, "end", None)
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > character_length
        ):
            issues.append(
                {
                    "code": "character_span_out_of_range",
                    "message": "Source-map span is not a nonempty character range inside the legal text.",
                    "field_path": path,
                }
            )
            continue
        passage = source_text[start:end]
        if passage == "":
            issues.append(
                {
                    "code": "empty_passage",
                    "message": "Character span selected an empty passage.",
                    "field_path": path,
                }
            )
    return issues


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

    formula_ids: List[str] = []
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
        formula_ids.append(rule_cid)

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
        if trace["fact_id"] in formula_ids and not trace.get("transformation_steps")
    ]
    coverage_ok = bool(formula_ids) and bool(stage_ids) and not missing_from_build
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
        "coverage_ok": (
            coverage_ok
            and validation.valid
            and built_validation.valid
            and binding.traceable
            and not transformations_missing
            and binding.emitted_fact_ids
        ),
    }


def _unsupported_diagnostics(result: Any, stages: Sequence[Any]) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    for item in getattr(result, "unsupported_semantics", ()) or ():
        payload = _jsonable(item.to_dict() if hasattr(item, "to_dict") else item)
        if isinstance(payload, dict):
            payload["origin"] = "result.unsupported_semantics"
            diagnostics.append(payload)
    for item in getattr(result, "diagnostics", ()) or ():
        payload = _jsonable(item.to_dict() if hasattr(item, "to_dict") else item)
        if isinstance(payload, dict):
            payload["origin"] = "result.diagnostics"
            diagnostics.append(payload)
    error = getattr(result, "error", None)
    if error is not None:
        payload = _jsonable(error.to_dict() if hasattr(error, "to_dict") else error)
        if isinstance(payload, dict):
            payload["origin"] = "result.error"
            diagnostics.append(payload)
    for stage in stages:
        for item in getattr(stage, "unsupported", ()) or ():
            payload = _jsonable(item)
            if isinstance(payload, dict):
                payload["origin"] = f"stage.{stage.stage_id}"
                diagnostics.append(payload)
    return diagnostics


def _stage_records(stages: Sequence[Any]) -> List[Dict[str, Any]]:
    return [_jsonable(stage.to_dict()) for stage in stages]


def _receipt_shell(
    *,
    status: str,
    capability: CanonicalCompilerCapability,
    identities: Mapping[str, Any] | None,
    reason: str,
    cache_outcome: str,
    prior_receipt_id: str = "",
    mismatched_fields: Sequence[str] = (),
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "schema_version": "canonical-formalization-receipt/v1",
        "status": status,
        "capability": capability.as_dict(),
        "identities": dict(identities or {}),
        "reason": reason,
        "cache_outcome": cache_outcome,
        "reused": cache_outcome == "reused",
        "prior_receipt_id": prior_receipt_id,
        "mismatched_fields": list(mismatched_fields),
        "entails_applicability": False,
        "entails_claim": False,
        "legal_text_separated_from_user_facts": True,
        "user_facts_included_in_source": False,
        "source_map": None,
        "source_map_validation": None,
        "traceability": None,
        "unsupported_diagnostics": [],
        "stages": [],
        "formula_ids": [],
        "passages": [],
    }
    if extra:
        body.update(dict(extra))
    encoded = json.dumps(
        {key: body[key] for key in ("status", "reason", "identities", "prior_receipt_id", "mismatched_fields")},
        sort_keys=True,
        default=str,
    )
    body["receipt_id"] = "canonical-receipt-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    return body


def _store_receipt(receipt: Dict[str, Any], *, cache_key: str = "") -> Dict[str, Any]:
    stored = deepcopy(receipt)
    _CANONICAL_FORMALIZATION_RECEIPTS[stored["receipt_id"]] = stored
    if cache_key and stored.get("status") == "success":
        _CANONICAL_FORMALIZATION_CACHE[cache_key] = stored["receipt_id"]
    return deepcopy(stored)


def _finish(receipt: Dict[str, Any]) -> Dict[str, Any]:
    capability = receipt.get("capability") if isinstance(receipt.get("capability"), Mapping) else {}
    return with_adapter_metadata(
        receipt,
        operation="compile_canonical_legal_ir",
        backend_available=bool(capability.get("available")),
        degraded_reason=capability.get("reason"),
        implementation_status=str(capability.get("status") or ""),
        extra_metadata={
            "canonical_support": capability.get("support"),
            "pipeline_cid": (receipt.get("identities") or {}).get("pipeline_cid", ""),
            "compiler_config_cid": (receipt.get("identities") or {}).get("compiler_config_cid", ""),
        },
    )


def compile_canonical_legal_ir(
    source_text: str,
    *,
    request_id: str,
    vocabulary: Mapping[str, Sequence[str]],
    legal_context: Mapping[str, Any] | None = None,
    user_facts: Sequence[str] | None = None,
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

    legal_text, legal_origin = _legal_source_text(source_text, legal_context)
    excluded_facts = [str(item) for item in (user_facts or ()) if str(item).strip()]
    authority_version = _version_from_context(legal_context)
    citation = _citation_from_context(legal_context, request_id)
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
            extra={"user_facts": excluded_facts, "authority_version": authority_version},
        )
        return _finish(_store_receipt(receipt))

    cache_key = _compile_cache_key(
        identities,
        source_cid=request.source_cid,
        request_id=str(request_id),
        vocabulary=atom_vocabulary.to_dict(),
        allow_explicit_partial=bool(allow_explicit_partial),
        authority_version=authority_version,
    )
    if use_cache and cache_key in _CANONICAL_FORMALIZATION_CACHE:
        cached_id = _CANONICAL_FORMALIZATION_CACHE[cache_key]
        cached = _CANONICAL_FORMALIZATION_RECEIPTS.get(cached_id)
        if cached is not None and cached.get("identities") == identities:
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
            extra={"user_facts": excluded_facts, "cache_key": cache_key},
        )
        return _finish(_store_receipt(receipt))

    result = pipeline.result
    stages = tuple(pipeline.stages)
    status_value = str(getattr(result.status, "value", result.status))
    diagnostics = _unsupported_diagnostics(result, stages)
    stage_payload = _stage_records(stages)
    observed_pipeline_cid = str(pipeline.pipeline_cid)
    if observed_pipeline_cid != identities["pipeline_cid"]:
        identities = dict(identities)
        identities["pipeline_cid"] = observed_pipeline_cid
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


def verify_canonical_formalization_receipt(
    receipt_id: str,
    *,
    source_text: str | None = None,
) -> Dict[str, Any]:
    """Re-check a stored receipt. Tampering does not delete the old receipt."""

    stored = inspect_canonical_formalization_receipt(receipt_id)
    if stored is None:
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason="Canonical formalization receipt was not found.")
        )
        return _finish(
            {
                "schema_version": "canonical-formalization-receipt/v1",
                "status": "unavailable",
                "receipt_id": str(receipt_id or ""),
                "capability": capability.as_dict(),
                "reason": capability.reason,
                "tampered": False,
                "identities": {},
            }
        )
    candidate = deepcopy(stored)
    if source_text is not None:
        candidate["source_text"] = source_text
    audit = audit_canonical_formalization_payload(candidate)
    audit["inspected_receipt_id"] = stored.get("receipt_id")
    audit["stored_status"] = stored.get("status")
    return _finish(audit)


def audit_canonical_formalization_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate source CID, character passages, and traceability on a receipt copy."""

    if not _canonical_modules_ready():
        capability = classify_canonical_compiler_capability(
            _canonical_evidence(reason=_canonical_import_reason())
        )
        return {
            "status": "unavailable",
            "tampered": False,
            "capability": capability.as_dict(),
            "reason": capability.reason,
            "issues": [],
        }
    source_text = str(payload.get("source_text") or "")
    issues: List[Dict[str, str]] = []
    try:
        expected_cid = _source_cid_for_text(source_text)
    except Exception as exc:  # noqa: BLE001 - typed integrity failure
        expected_cid = ""
        issues.append({"code": "source_cid_unavailable", "message": str(exc), "field_path": "source_text"})
    recorded_cid = str(payload.get("source_cid") or "")
    if expected_cid and recorded_cid and expected_cid != recorded_cid:
        issues.append(
            {
                "code": "source_text_tampered",
                "message": "Source text does not match the receipt source CID.",
                "field_path": "source_text",
            }
        )
    for index, passage in enumerate(payload.get("passages") or []):
        if not isinstance(passage, Mapping):
            issues.append(
                {"code": "passage_invalid", "message": "Passage record is not an object.", "field_path": f"passages[{index}]"}
            )
            continue
        start = passage.get("start")
        end = passage.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end > len(source_text) or start < 0:
            issues.append(
                {
                    "code": "character_span_out_of_range",
                    "message": "Stored passage is outside the source character length.",
                    "field_path": f"passages[{index}]",
                }
            )
            continue
        selected = source_text[start:end]
        if selected != passage.get("passage"):
            issues.append(
                {
                    "code": "passage_tampered",
                    "message": "Stored passage does not match the source character span.",
                    "field_path": f"passages[{index}].passage",
                }
            )
    source_map = payload.get("source_map")
    validation_payload: Dict[str, Any] | None = None
    traceable = False
    if isinstance(source_map, Mapping) and payload.get("formula_ids"):
        source_maps = _canonical_source_map_module
        validation = source_maps.validate_legal_ir_source_map(source_map)
        validation_payload = validation.to_dict()
        if not validation.valid:
            issues.append(
                {
                    "code": "source_map_invalid",
                    "message": "Stored source map failed validation.",
                    "field_path": "source_map",
                }
            )
        binding = source_maps.bind_legal_ir_artifact_source_map(
            {"emitted_fact_ids": list(payload.get("formula_ids") or [])},
            source_map,
            artifact_kind="compiler_formula",
            emitted_fact_ids=tuple(payload.get("formula_ids") or ()),
        )
        traceable = bool(binding.traceable)
        if not traceable:
            issues.append(
                {
                    "code": "traceability_failed",
                    "message": "Stored formulas are not traceable.",
                    "field_path": "formula_ids",
                }
            )
        for fact_id in payload.get("formula_ids") or []:
            trace = source_maps.trace_legal_ir_fact(source_map, fact_id)
            if not trace.transformation_steps or not trace.source_spans:
                issues.append(
                    {
                        "code": "transformation_trace_missing",
                        "message": "Formula does not trace to both a source passage and a transformation.",
                        "field_path": f"traces.{fact_id}",
                    }
                )
                traceable = False
    tampered = any(item["code"].endswith("tampered") or item["code"].endswith("_tampered") for item in issues) or any(
        item["code"] in {"source_text_tampered", "passage_tampered"} for item in issues
    )
    status = "tampered" if issues else "verified"
    capability = classify_canonical_compiler_capability(
        _canonical_evidence(
            executed=not issues and payload.get("status") == "success",
            status="success" if not issues and payload.get("status") == "success" else "failed",
            traceable=traceable and not issues,
            source_map_valid=bool(validation_payload and validation_payload.get("valid")) and not issues,
            tampered=bool(issues),
            reason="" if not issues else "Canonical formalization receipt failed integrity checks.",
        )
    )
    return {
        "schema_version": "canonical-formalization-audit/v1",
        "status": status,
        "tampered": bool(issues),
        "capability": capability.as_dict(),
        "reason": "" if not issues else capability.reason,
        "issues": issues,
        "source_map_validation": validation_payload,
        "traceable": traceable and not issues,
        "identities": dict(payload.get("identities") or {}),
        "receipt_id": payload.get("receipt_id"),
    }


def legacy_procedural_template_attributes() -> Dict[str, Any]:
    return {
        "category": "civil_procedure",
        "record_kind": "legal_requirement",
        "about_complainant": False,
        "verification_status": "unverified_template",
        "promotion_status": "unverified_template",
        "applicable": False,
        "legacy_template": True,
        "template_kind": "procedural_template",
        "review_reason": "legacy_unverified_template",
        "source_bound": False,
    }


__all__ = [
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "LOGIC_AVAILABLE",
    "LOGIC_CAPABILITY_SCHEMA_VERSION",
    "LOGIC_ERROR",
    "Z3_AVAILABLE",
    "LOCAL_FORMAL_LOGIC_AVAILABLE",
    "LOCAL_FORMAL_LOGIC_PATH",
    "REASONER_BRIDGE_AVAILABLE",
    "REASONER_BRIDGE_ERROR",
    "LogicCapabilityState",
    "LogicCapabilityStatus",
    "get_logic_capabilities",
    "get_logic_capability",
    "get_logic_capability_report",
    "require_logic_capability",
    "text_to_fol",
    "legal_text_to_deontic",
    "prove_claim_elements",
    "check_contradictions",
    "run_hybrid_reasoning",
    "export_theorem_from_proof_bundle",
    "get_predicate_templates",
    "map_claim_elements_to_predicates",
    "_COMPLAINT_PREDICATE_TEMPLATES",
    "SOURCE_BOUND_RULE_CONTRACT",
    "extract_source_bound_rule_candidates",
    "evaluate_temporal_requirement_applicability",
    "is_applicable_legal_requirement",
    "requirement_treatment_support",
    "legacy_procedural_template_attributes",
    "legacy_unverified_requirement_templates",
    "sha256_utf8",
    "CanonicalCompilerCapability",
    "CanonicalCompilerSupport",
    "audit_canonical_formalization_payload",
    "canonical_compiler_identities",
    "compile_canonical_legal_ir",
    "get_canonical_compiler_capability",
    "inspect_canonical_formalization_receipt",
    "reset_canonical_formalization_cache",
    "verify_canonical_formalization_receipt",
]
