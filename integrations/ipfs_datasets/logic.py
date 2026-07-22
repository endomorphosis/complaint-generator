from __future__ import annotations

from collections import Counter
from copy import deepcopy
import inspect
from typing import Any, Dict, Iterable, List

from lib.formal_logic.capabilities import (
    FormalLogicCapability,
    FormalLogicCapabilityError,
    FormalLogicDegradedError,
    FormalLogicOperation,
    FormalLogicUnavailableError,
    LogicCapabilityState,
    LogicCapabilityStatus,
)
from lib.formal_logic.frames import FrameKnowledgeBase

from .loader import import_module_optional
from .types import with_adapter_metadata


_logic_module, _logic_error = import_module_optional("ipfs_datasets_py.logic")
_fol_module, _fol_error = import_module_optional("ipfs_datasets_py.logic.fol")
_deontic_module, _deontic_error = import_module_optional("ipfs_datasets_py.logic.deontic")
_tdfol_module, _tdfol_error = import_module_optional("ipfs_datasets_py.logic.TDFOL")
_z3_module, _z3_error = import_module_optional(
    "ipfs_datasets_py.logic.external_provers.smt.z3_prover_bridge"
)
_reasoner_module, _reasoner_error = import_module_optional(
    "ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
)
if _reasoner_module is None:
    _reasoner_module, _reasoner_error = import_module_optional(
        "ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
    )

LOGIC_AVAILABLE = any(
    value is not None
    for value in (_logic_module, _fol_module, _deontic_module, _tdfol_module)
)
LOGIC_ERROR = _logic_error or _fol_error or _deontic_error or _tdfol_error or _z3_error
REASONER_BRIDGE_AVAILABLE = _reasoner_module is not None
REASONER_BRIDGE_ERROR = _reasoner_error
REASONER_BRIDGE_PATH = getattr(_reasoner_module, "__name__", "") if _reasoner_module is not None else ""
LOCAL_FORMAL_LOGIC_AVAILABLE = True
LOCAL_FORMAL_LOGIC_PATH = "lib.formal_logic"
LOGIC_CAPABILITY_SCHEMA_VERSION = "formal-logic-capabilities/v1"

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
    return {
        "schema_version": LOGIC_CAPABILITY_SCHEMA_VERSION,
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


def _normalize_logic_payload(payload_or_predicates: Any) -> Dict[str, Any]:
    if isinstance(payload_or_predicates, dict):
        raw_predicates = payload_or_predicates.get("predicates")
        predicates = raw_predicates if isinstance(raw_predicates, list) else []
        temporal_reasoning_payload = payload_or_predicates.get("temporal_reasoning_payload")
        return {
            "predicates": [predicate for predicate in predicates if isinstance(predicate, dict)],
            "temporal_reasoning_payload": temporal_reasoning_payload if isinstance(temporal_reasoning_payload, dict) else {},
            "claim_support_temporal_handoff": _normalize_claim_support_temporal_handoff(
                payload_or_predicates.get("claim_support_temporal_handoff")
            ),
            "claim_reasoning_review": _normalize_claim_reasoning_review(
                payload_or_predicates.get("claim_reasoning_review")
            ),
            "payload_keys": sorted(payload_or_predicates.keys()),
        }

    return {
        "predicates": [predicate for predicate in payload_or_predicates if isinstance(predicate, dict)],
        "temporal_reasoning_payload": {},
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
            claim_elements.append(
                {
                    "claim_symbol": claim_symbol,
                    "claim_type": claim_type,
                    "claim_element_id": predicate.get("claim_element_id"),
                    "claim_element_text": predicate.get("claim_element_text"),
                    "coverage_status": predicate.get("coverage_status"),
                }
            )
        elif predicate_type == "support_trace":
            trace_symbol = _normalize_logic_symbol(predicate.get("predicate_id") or predicate.get("support_ref"), prefix="support")
            support_traces.append(
                {
                    "support_symbol": trace_symbol,
                    "claim_type": claim_type,
                    "support_ref": predicate.get("support_ref"),
                    "support_kind": predicate.get("support_kind"),
                    "text": predicate.get("text") or "",
                }
            )
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
    normalized_handoff = _normalize_claim_support_temporal_handoff(claim_support_temporal_handoff)
    if normalized_handoff:
        temporal_reasoning_payload["claim_support_temporal_handoff"] = normalized_handoff
        temporal_reasoning_payload["theorem_export_metadata"] = _build_theorem_export_metadata(normalized_handoff)
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


def _build_reasoner_proof_artifact(
    predicates: Iterable[Dict[str, Any]],
    temporal_reasoning_payload: Dict[str, Any],
    claim_support_temporal_handoff: Dict[str, Any],
) -> Dict[str, Any]:
    if not REASONER_BRIDGE_AVAILABLE or _reasoner_module is None:
        return {
            "available": False,
            "status": "unavailable",
            "reason": str(REASONER_BRIDGE_ERROR or "reasoner_bridge_unavailable"),
        }

    run_pipeline = getattr(_reasoner_module, "run_v2_pipeline_with_defaults", None)
    check_compliance = getattr(_reasoner_module, "check_compliance", None)
    explain_proof = getattr(_reasoner_module, "explain_proof", None)
    if not callable(run_pipeline) or not callable(check_compliance) or not callable(explain_proof):
        return {
            "available": False,
            "status": "unavailable",
            "reason": "reasoner_bridge_missing_entrypoints",
        }

    sentence = _derive_reasoner_sentence(predicates, temporal_reasoning_payload)
    if not sentence:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "missing_reasoner_sentence",
        }

    theorem_export_metadata = dict(temporal_reasoning_payload.get("theorem_export_metadata") or {})
    try:
        pipeline_kwargs = {
            "theorem_export_metadata": theorem_export_metadata,
            "claim_support_temporal_handoff": claim_support_temporal_handoff,
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
        }
    except Exception as exc:
        return {
            "available": False,
            "status": "error",
            "reason": str(exc),
            "sentence": sentence,
            "theorem_export_metadata": theorem_export_metadata,
            "claim_support_temporal_handoff": dict(claim_support_temporal_handoff or {}),
        }


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


def text_to_fol(text: str, *, require_implemented: bool = False) -> Dict[str, Any]:
    """Return text-to-FOL diagnostics at the operation's actual capability tier.

    Strict workflows should set ``require_implemented``.  The typed gate then
    fails before an empty structural result can be mistaken for conversion.
    """

    capability = get_logic_capability(FormalLogicOperation.TEXT_TO_FOL)
    if require_implemented:
        capability.require_implemented()
    return with_adapter_metadata(
        {
            "status": capability.state.value,
            "predicates": [],
            "source_text": text,
            "capability": capability.as_dict(),
        },
        operation="text_to_fol",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=capability.state.value,
        extra_metadata=_logic_operation_metadata(capability),
    )


def legal_text_to_deontic(
    text: str,
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Return legal-text translation at the operation's capability tier."""

    capability = get_logic_capability(FormalLogicOperation.LEGAL_TEXT_TO_DEONTIC)
    if require_implemented:
        capability.require_implemented()
    return with_adapter_metadata(
        {
            "status": capability.state.value,
            "norms": [],
            "source_text": text,
            "capability": capability.as_dict(),
        },
        operation="legal_text_to_deontic",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=capability.state.value,
        extra_metadata=_logic_operation_metadata(capability),
    )


def prove_claim_elements(
    predicates: Iterable[Dict[str, Any]] | Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Build proof inputs, optionally requiring authoritative proof support."""

    capability = get_logic_capability(FormalLogicOperation.PROVE_CLAIM_ELEMENTS)
    if require_implemented:
        capability.require_implemented()
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    temporal_reasoning_payload = _build_temporal_reasoning_payload(
        predicate_list,
        claim_support_temporal_handoff=normalized_payload["claim_support_temporal_handoff"],
        claim_reasoning_review=normalized_payload["claim_reasoning_review"],
    )
    return with_adapter_metadata(
        {
            "status": capability.state.value,
            "provable_elements": [],
            "unprovable_elements": [],
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "capability": capability.as_dict(),
        },
        operation="prove_claim_elements",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=capability.state.value,
        extra_metadata={
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            **_logic_operation_metadata(capability),
        },
    )


def check_contradictions(
    predicates: Iterable[Dict[str, Any]] | Dict[str, Any],
    *,
    require_implemented: bool = False,
) -> Dict[str, Any]:
    """Extract contradiction signals at the reported capability tier."""

    capability = get_logic_capability(FormalLogicOperation.CHECK_CONTRADICTIONS)
    if require_implemented:
        capability.require_implemented()
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    temporal_reasoning_payload = _build_temporal_reasoning_payload(
        predicate_list,
        claim_support_temporal_handoff=normalized_payload["claim_support_temporal_handoff"],
        claim_reasoning_review=normalized_payload["claim_reasoning_review"],
    )
    return with_adapter_metadata(
        {
            "status": capability.state.value,
            "contradictions": [],
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "capability": capability.as_dict(),
        },
        operation="check_contradictions",
        backend_available=capability.available,
        degraded_reason=capability.reason,
        implementation_status=capability.state.value,
        extra_metadata={
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
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
    predicate_summary = _summarize_predicates(predicates)

    if isinstance(bridge_payload, dict) and bridge_payload:
        temporal_reasoning_payload = deepcopy(bridge_payload)
    else:
        temporal_reasoning_payload = _build_temporal_reasoning_payload(
            predicates,
            claim_support_temporal_handoff=claim_support_temporal_handoff,
            claim_reasoning_review=claim_reasoning_review,
        )

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

    proof_artifact = _build_reasoner_proof_artifact(
        predicates,
        temporal_reasoning_payload,
        claim_support_temporal_handoff,
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
            "timeline_event_count": len(temporal_reasoning_payload.get("timeline_events", []) or []),
            "temporal_relation_count": len(temporal_reasoning_payload.get("temporal_relations", []) or []),
            "contradiction_signal_count": len(temporal_reasoning_payload.get("contradiction_signals", []) or []),
            "reasoning_mode": "temporal_bridge",
            "compiler_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "proof_artifact": proof_artifact,
            "local_logic_snapshot": local_logic_snapshot,
            "claim_reasoning_review": deepcopy(temporal_reasoning_payload.get("claim_reasoning_review") or {}),
            "compiler_bridge_path": (
                REASONER_BRIDGE_PATH if REASONER_BRIDGE_AVAILABLE else ""
            ),
        },
        "payload_keys": normalized_payload["payload_keys"],
        "predicate_count": predicate_summary.get("predicate_count", 0),
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
        },
    )


__all__ = [
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "LOGIC_AVAILABLE",
    "LOGIC_CAPABILITY_SCHEMA_VERSION",
    "LOGIC_ERROR",
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
]
