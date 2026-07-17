from __future__ import annotations

from collections import Counter
from copy import deepcopy
import inspect
import re
from typing import Any, Dict, Iterable, List, Tuple

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
    for value in (_logic_module, _fol_module, _deontic_module, _tdfol_module)
)
LOGIC_ERROR = _logic_error or _fol_error or _deontic_error or _tdfol_error or _z3_error
Z3_AVAILABLE = _z3_module is not None or _local_z3_module is not None
REASONER_BRIDGE_AVAILABLE = _reasoner_module is not None
REASONER_BRIDGE_ERROR = _reasoner_error
REASONER_BRIDGE_PATH = getattr(_reasoner_module, "__name__", "") if _reasoner_module is not None else ""
LOCAL_FORMAL_LOGIC_AVAILABLE = True
LOCAL_FORMAL_LOGIC_PATH = "lib.formal_logic"

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
            "explanation": explanation if isinstance(explanation, dict) else {},
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


def text_to_fol(text: str) -> Dict[str, Any]:
    """Convert *text* to First-Order Logic predicates.

    Tries the ``ipfs_datasets_py.logic.fol.FOLConverter`` from the submodule
    first.  Falls back to local regex-based extraction when the upstream
    module is unavailable.
    """
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
                    },
                    operation="text_to_fol",
                    backend_available=True,
                    implementation_status="implemented",
                    extra_metadata={
                        "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
                        "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
                    },
                )
        except Exception:
            pass

    # --- Local regex fallback ---
    predicates = _local_extract_fol_predicates(str(text or ""))
    return with_adapter_metadata(
        {
            "status": "success",
            "predicates": predicates,
            "source_text": str(text or ""),
            "converter": "local_regex_fallback",
        },
        operation="text_to_fol",
        backend_available=LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not LOGIC_AVAILABLE else None,
        implementation_status="implemented",
        extra_metadata={
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
        },
    )


def legal_text_to_deontic(text: str) -> Dict[str, Any]:
    """Convert legal *text* to deontic logic norms.

    Tries ``ipfs_datasets_py.logic.deontic.DeonticConverter`` first, then
    supplements (or falls back) to local pattern-based extraction.

    The upstream converter returns a single ``DeonticFormula`` per call.  We
    wrap it into the same list format as the local extractor.  When the
    upstream result is empty the local extractor is used as a supplement so
    that well-known prohibition/obligation patterns are never silently dropped.
    """
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
            "status": "success",
            "norms": norms,
            "source_text": str(text or ""),
            "converter": converter_used,
        },
        operation="legal_text_to_deontic",
        backend_available=upstream_available or LOGIC_AVAILABLE,
        degraded_reason=LOGIC_ERROR if not (upstream_available or LOGIC_AVAILABLE) else None,
        implementation_status="implemented",
        extra_metadata={
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
        },
    )


def prove_claim_elements(predicates: Iterable[Dict[str, Any]] | Dict[str, Any]) -> Dict[str, Any]:
    """Prove or refute claim elements by running the hybrid reasoning pipeline.

    Delegates to :func:`run_hybrid_reasoning` so that both the upstream
    ``hybrid_v2_blueprint`` reasoner bridge *and* the local TDFOL/DCEC bridge
    are tried in priority order.  The return value includes ``provable_elements``
    and ``unprovable_elements`` extracted from the proof artifact.

    Contradiction detection is performed by :func:`check_contradictions` and
    the count is included as ``contradiction_count`` in the result.
    """
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)

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
            {"temporal_reasoning_payload": temporal_reasoning_payload, "proof_artifact": proof_artifact},
        )
    except Exception:
        pass

    return with_adapter_metadata(
        {
            "status": "success" if proof_status not in {"error", "failed"} else "error",
            "provable_elements": provable_elements,
            "unprovable_elements": unprovable_elements,
            "proof_status": proof_status,
            "violation_count": violation_count,
            "contradiction_count": contradiction_count,
            "contradictions": contradiction_list,
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "proof_artifact": proof_artifact,
            "theorem_export": theorem_export,
        },
        operation="prove_claim_elements",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
            "reasoner_bridge_available": REASONER_BRIDGE_AVAILABLE,
            "theorem_export_version": theorem_export.get("export_version") or "",
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


def check_contradictions(predicates: Iterable[Dict[str, Any]] | Dict[str, Any]) -> Dict[str, Any]:
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
    normalized_payload = _normalize_logic_payload(predicates)
    predicate_list = normalized_payload["predicates"]
    predicate_summary = _summarize_predicates(predicate_list)
    temporal_reasoning_payload = _build_temporal_reasoning_payload(
        predicate_list,
        claim_support_temporal_handoff=normalized_payload["claim_support_temporal_handoff"],
        claim_reasoning_review=normalized_payload["claim_reasoning_review"],
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
            "status": "success",
            "contradictions": contradictions,
            "contradiction_count": len(contradictions),
            "has_contradictions": bool(contradictions),
            "proof_status": proof_status,
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
        },
        operation="check_contradictions",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={
            **predicate_summary,
            "temporal_reasoning_payload": temporal_reasoning_payload,
            "local_formal_logic_available": LOCAL_FORMAL_LOGIC_AVAILABLE,
            "local_formal_logic_path": LOCAL_FORMAL_LOGIC_PATH,
        },
    )


def run_hybrid_reasoning(payload: Dict[str, Any]) -> Dict[str, Any]:
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
        backend_available=True,
        degraded_reason=str(REASONER_BRIDGE_ERROR) if REASONER_BRIDGE_ERROR and not REASONER_BRIDGE_AVAILABLE else None,
        implementation_status="implemented",
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
        },
    )




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

    for element in (list(elements) if not isinstance(elements, list) else elements):
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or element.get("label") or "")
        coverage_status = str(element.get("status") or element.get("coverage_status") or "missing")
        predicate_id = element.get("predicate_id") or f"{claim_type}:{element_id}" if element_id else f"{claim_type}:unknown"

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
        }
        predicates.append(predicate)

    return with_adapter_metadata(
        {
            "status": "success",
            "claim_type": claim_type,
            "predicates": predicates,
            "predicate_count": len(predicates),
            "template_match_count": template_match_count,
            "unmapped_element_ids": unmapped_element_ids,
        },
        operation="map_claim_elements_to_predicates",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={"claim_type": claim_type, "element_count": len(predicates)},
    )


__all__ = [
    "LOGIC_AVAILABLE",
    "LOGIC_ERROR",
    "Z3_AVAILABLE",
    "LOCAL_FORMAL_LOGIC_AVAILABLE",
    "LOCAL_FORMAL_LOGIC_PATH",
    "REASONER_BRIDGE_AVAILABLE",
    "REASONER_BRIDGE_ERROR",
    "text_to_fol",
    "legal_text_to_deontic",
    "prove_claim_elements",
    "check_contradictions",
    "run_hybrid_reasoning",
    "get_predicate_templates",
    "map_claim_elements_to_predicates",
    "_COMPLAINT_PREDICATE_TEMPLATES",
]