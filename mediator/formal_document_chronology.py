"""Chronology helpers extracted from formal complaint document assembly."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .formal_document import (
    _chronology_fact_label,
    _claim_chronology_focus_families,
    _clean_sentence,
    _clean_text,
    _contains_temporal_sequence_marker,
    _format_timeline_date,
    _join_chronology_segments,
    _normalize_theorem_export_metadata_for_drafting,
)

def _formalize_allegation_fragment(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -;")
    if not text:
        return ""
    replacements = (
        (r"^i was\b", "Plaintiff was"),
        (r"^i am\b", "Plaintiff is"),
        (r"^i need\b", "Plaintiff needs"),
        (r"^i needed\b", "Plaintiff needed"),
        (r"^i lost\b", "Plaintiff lost"),
        (r"^i asked\b", "Plaintiff asked"),
        (r"^i reported\b", "Plaintiff reported"),
        (r"^i complained\b", "Plaintiff complained"),
        (r"^i informed\b", "Plaintiff informed"),
        (r"^i notified\b", "Plaintiff notified"),
        (r"^i requested\b", "Plaintiff requested"),
        (r"^i sought\b", "Plaintiff sought"),
        (r"^i experienced\b", "Plaintiff experienced"),
        (r"^i suffered\b", "Plaintiff suffered"),
        (r"^i told\b", "Plaintiff told"),
        (r"^they\b", "Defendant"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    clause_replacements = (
        (r"([,;]\s+)i was\b", r"\1Plaintiff was"),
        (r"([,;]\s+)i am\b", r"\1Plaintiff is"),
        (r"([,;]\s+)i need\b", r"\1Plaintiff needs"),
        (r"([,;]\s+)i needed\b", r"\1Plaintiff needed"),
        (r"([,;]\s+)i lost\b", r"\1Plaintiff lost"),
        (r"([,;]\s+)i asked\b", r"\1Plaintiff asked"),
        (r"([,;]\s+)i reported\b", r"\1Plaintiff reported"),
        (r"([,;]\s+)i complained\b", r"\1Plaintiff complained"),
        (r"([,;]\s+)i requested\b", r"\1Plaintiff requested"),
        (r"([,;]\s+)i informed\b", r"\1Plaintiff informed"),
        (r"([,;]\s+)i notified\b", r"\1Plaintiff notified"),
        (r"([,;]\s+)i suffered\b", r"\1Plaintiff suffered"),
        (r"([,;]\s+)i experienced\b", r"\1Plaintiff experienced"),
        (r"([,;]\s+)i told\b", r"\1Plaintiff told"),
        (r"(\band\s+)i was\b", r"\1Plaintiff was"),
        (r"(\band\s+)i am\b", r"\1Plaintiff is"),
        (r"(\band\s+)i need\b", r"\1Plaintiff needs"),
        (r"(\band\s+)i needed\b", r"\1Plaintiff needed"),
        (r"(\band\s+)i lost\b", r"\1Plaintiff lost"),
        (r"(\band\s+)i asked\b", r"\1Plaintiff asked"),
        (r"(\band\s+)i reported\b", r"\1Plaintiff reported"),
        (r"(\band\s+)i complained\b", r"\1Plaintiff complained"),
        (r"(\band\s+)i requested\b", r"\1Plaintiff requested"),
        (r"(\band\s+)i informed\b", r"\1Plaintiff informed"),
        (r"(\band\s+)i notified\b", r"\1Plaintiff notified"),
        (r"(\band\s+)i suffered\b", r"\1Plaintiff suffered"),
        (r"(\band\s+)i experienced\b", r"\1Plaintiff experienced"),
        (r"(\band\s+)i told\b", r"\1Plaintiff told"),
        (r"(\bafter\s+)i was\b", r"\1Plaintiff was"),
        (r"(\bafter\s+)i am\b", r"\1Plaintiff is"),
        (r"(\bafter\s+)i need\b", r"\1Plaintiff needs"),
        (r"(\bafter\s+)i needed\b", r"\1Plaintiff needed"),
        (r"(\bafter\s+)i lost\b", r"\1Plaintiff lost"),
        (r"(\bafter\s+)i asked\b", r"\1Plaintiff asked"),
        (r"(\bafter\s+)i reported\b", r"\1Plaintiff reported"),
        (r"(\bafter\s+)i complained\b", r"\1Plaintiff complained"),
        (r"(\bafter\s+)i requested\b", r"\1Plaintiff requested"),
        (r"(\bafter\s+)i informed\b", r"\1Plaintiff informed"),
        (r"(\bafter\s+)i notified\b", r"\1Plaintiff notified"),
        (r"(\bafter\s+)i suffered\b", r"\1Plaintiff suffered"),
        (r"(\bafter\s+)i experienced\b", r"\1Plaintiff experienced"),
        (r"(\bafter\s+)i told\b", r"\1Plaintiff told"),
        (r"(\bthat\s+)i am\b", r"\1Plaintiff is"),
        (r"(\bthat\s+)i need\b", r"\1Plaintiff needs"),
        (r"(\bthat\s+)i needed\b", r"\1Plaintiff needed"),
        (r"(\bthat\s+)i asked\b", r"\1Plaintiff asked"),
        (r"(\bthat\s+)i complained\b", r"\1Plaintiff complained"),
        (r"(\bthat\s+)i requested\b", r"\1Plaintiff requested"),
        (r"(\bthat\s+)i told\b", r"\1Plaintiff told"),
    )
    for pattern, replacement in clause_replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\bmy\b", "Plaintiff's", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmine\b", "Plaintiff's", text, flags=re.IGNORECASE)
    text = re.sub(r"\bme\b", "Plaintiff", text, flags=re.IGNORECASE)
    text = re.sub(r"\blost Plaintiff's pay and benefits\b", "lost pay and benefits", text, flags=re.IGNORECASE)
    text = re.sub(r"\blost Plaintiff's (pay|wages|salary|income|benefits)\b", r"lost \1", text, flags=re.IGNORECASE)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    if len(text) < 12:
        return ""
    return text if text.endswith((".", "?", "!")) else f"{text}."
def _build_anchored_chronology_summary(intake_case_file: Dict[str, Any], *, limit: int = 3) -> List[str]:
    facts = [dict(item) for item in list(intake_case_file.get("canonical_facts") or []) if isinstance(item, dict)]
    relations = [dict(item) for item in list(intake_case_file.get("timeline_relations") or []) if isinstance(item, dict)]
    if not facts or not relations:
        return []

    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if str(fact.get("fact_id") or "").strip()
    }
    relation_records = []
    for relation in relations:
        if str(relation.get("relation_type") or "").strip().lower() != "before":
            continue
        source_id = str(relation.get("source_fact_id") or "").strip()
        target_id = str(relation.get("target_fact_id") or "").strip()
        source_fact = fact_by_id.get(source_id)
        target_fact = fact_by_id.get(target_id)
        if not source_fact or not target_fact:
            continue
        source_date = _format_timeline_date((source_fact.get("temporal_context") or {}).get("start_date") or relation.get("source_start_date"))
        target_date = _format_timeline_date((target_fact.get("temporal_context") or {}).get("start_date") or relation.get("target_start_date"))
        if not source_date or not target_date:
            continue
        relation_records.append(
            {
                "key": (source_id, target_id),
                "source_id": source_id,
                "target_id": target_id,
                "source_fact": source_fact,
                "target_fact": target_fact,
                "source_date": source_date,
                "target_date": target_date,
            }
        )
    if not relation_records:
        return []

    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming_count: Dict[str, int] = {}
    for record in relation_records:
        outgoing.setdefault(record["source_id"], []).append(record)
        incoming_count[record["target_id"]] = incoming_count.get(record["target_id"], 0) + 1
        incoming_count.setdefault(record["source_id"], incoming_count.get(record["source_id"], 0))

    lines: List[str] = []
    seen = set()
    used_keys = set()
    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        if incoming_count.get(record["source_id"], 0) != 0 or len(outgoing.get(record["source_id"], [])) != 1:
            continue
        chain = [record]
        next_id = record["target_id"]
        temp_used = {record["key"]}
        while len(outgoing.get(next_id, [])) == 1 and incoming_count.get(next_id, 0) == 1:
            next_record = outgoing[next_id][0]
            if next_record["key"] in temp_used:
                break
            chain.append(next_record)
            temp_used.add(next_record["key"])
            next_id = next_record["target_id"]
        if len(chain) < 2:
            continue
        segments = [
            f"{_chronology_fact_label(chain[0]['source_fact'])} on {chain[0]['source_date']}"
        ]
        segments.extend(
            f"{_chronology_fact_label(item['target_fact'])} on {item['target_date']}"
            for item in chain
        )
        line = f"{_join_chronology_segments(segments)} occurred in sequence."
        last_target = chain[-1]["target_fact"]
        target_context = last_target.get("temporal_context") if isinstance(last_target.get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f" The later date is derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        used_keys.update(temp_used)
        lines.append(line)

    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        source_label = _chronology_fact_label(record["source_fact"])
        target_label = _chronology_fact_label(record["target_fact"]).lower()
        line = f"{source_label} on {record['source_date']} preceded {target_label} on {record['target_date']}."
        target_context = record["target_fact"].get("temporal_context") if isinstance(record["target_fact"].get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f" The later date is derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines
def _build_claim_chronology_support(
    intake_case_file: Dict[str, Any],
    *,
    claim_type: str,
    claim_name: str,
    limit: int = 2,
) -> List[str]:
    facts = [dict(item) for item in list(intake_case_file.get("canonical_facts") or []) if isinstance(item, dict)]
    relations = [dict(item) for item in list(intake_case_file.get("timeline_relations") or []) if isinstance(item, dict)]
    if not facts or not relations:
        return []

    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if str(fact.get("fact_id") or "").strip()
    }
    focus_families = _claim_chronology_focus_families(claim_type, claim_name)
    relation_records = []
    for relation in relations:
        if str(relation.get("relation_type") or "").strip().lower() != "before":
            continue
        source_id = str(relation.get("source_fact_id") or "").strip()
        target_id = str(relation.get("target_fact_id") or "").strip()
        source_fact = fact_by_id.get(source_id)
        target_fact = fact_by_id.get(target_id)
        if not source_fact or not target_fact:
            continue
        source_date = _format_timeline_date((source_fact.get("temporal_context") or {}).get("start_date") or relation.get("source_start_date"))
        target_date = _format_timeline_date((target_fact.get("temporal_context") or {}).get("start_date") or relation.get("target_start_date"))
        if not source_date or not target_date:
            continue
        relation_records.append(
            {
                "key": (source_id, target_id),
                "source_id": source_id,
                "target_id": target_id,
                "source_fact": source_fact,
                "target_fact": target_fact,
                "source_date": source_date,
                "target_date": target_date,
                "source_family": str(source_fact.get("predicate_family") or "").strip().lower(),
                "target_family": str(target_fact.get("predicate_family") or "").strip().lower(),
            }
        )
    if not relation_records:
        return []

    filtered_records = [
        record for record in relation_records
        if not focus_families or ({record['source_family'], record['target_family']} & focus_families)
    ]
    if not filtered_records:
        filtered_records = relation_records

    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming_count: Dict[str, int] = {}
    for record in filtered_records:
        outgoing.setdefault(record["source_id"], []).append(record)
        incoming_count[record["target_id"]] = incoming_count.get(record["target_id"], 0) + 1
        incoming_count.setdefault(record["source_id"], incoming_count.get(record["source_id"], 0))

    lines: List[str] = []
    seen = set()
    fallback_lines: List[str] = []

    used_keys = set()
    for record in filtered_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        if incoming_count.get(record["source_id"], 0) != 0 or len(outgoing.get(record["source_id"], [])) != 1:
            continue
        chain = [record]
        next_id = record["target_id"]
        temp_used = {record["key"]}
        while len(outgoing.get(next_id, [])) == 1 and incoming_count.get(next_id, 0) == 1:
            next_record = outgoing[next_id][0]
            if next_record["key"] in temp_used:
                break
            chain.append(next_record)
            temp_used.add(next_record["key"])
            next_id = next_record["target_id"]
        if len(chain) < 2:
            continue
        segments = [
            f"{_chronology_fact_label(chain[0]['source_fact']).lower()} on {chain[0]['source_date']}"
        ]
        segments.extend(
            f"{_chronology_fact_label(item['target_fact']).lower()} on {item['target_date']}"
            for item in chain
        )
        line = f"The chronology shows {_join_chronology_segments(segments)} in sequence."
        last_target = chain[-1]["target_fact"]
        target_context = last_target.get("temporal_context") if isinstance(last_target.get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f" The later date is derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        used_keys.update(temp_used)
        lines.append(line)

    for record in filtered_records:
        if record["key"] in used_keys:
            continue
        source_label = _chronology_fact_label(record["source_fact"])
        target_label = _chronology_fact_label(record["target_fact"]).lower()
        line = f"The chronology shows {source_label.lower()} on {record['source_date']} before {target_label} on {record['target_date']}."
        target_context = record["target_fact"].get("temporal_context") if isinstance(record["target_fact"].get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f" The later date is derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        fallback_lines.append(line)

    if lines:
        return lines
    if fallback_lines:
        return fallback_lines[:1]
    return []
def _build_claim_reasoning_temporal_fallbacks(
    validation_claim: Any,
    *,
    claim_type: str,
    claim_name: str,
    limit: int = 2,
) -> Tuple[List[str], List[Dict[str, str]]]:
    claim_validation = validation_claim if isinstance(validation_claim, dict) else {}
    elements = claim_validation.get("elements") if isinstance(claim_validation.get("elements"), list) else []
    support_lines: List[str] = []
    gap_hints: List[Dict[str, str]] = []
    seen_support = set()
    seen_hints = set()

    for element in elements:
        if not isinstance(element, dict):
            continue
        reasoning = element.get("reasoning_diagnostics")
        if not isinstance(reasoning, dict):
            reasoning = {}
        hybrid_reasoning = reasoning.get("hybrid_reasoning")
        if not isinstance(hybrid_reasoning, dict):
            hybrid_reasoning = {}
        hybrid_result = hybrid_reasoning.get("result")
        if not isinstance(hybrid_result, dict):
            hybrid_result = {}
        proof_artifact = hybrid_result.get("proof_artifact")
        if not isinstance(proof_artifact, dict):
            proof_artifact = {}
        temporal_proof_bundle = reasoning.get("temporal_proof_bundle")
        if not isinstance(temporal_proof_bundle, dict):
            temporal_proof_bundle = {}
        theorem_exports = temporal_proof_bundle.get("theorem_exports")
        if not isinstance(theorem_exports, dict):
            theorem_exports = {}

        proof_metadata = _normalize_theorem_export_metadata_for_drafting(
            proof_artifact.get("theorem_export_metadata")
        )
        bundle_metadata = _normalize_theorem_export_metadata_for_drafting(
            theorem_exports.get("theorem_export_metadata")
        )
        active_metadata = proof_metadata if proof_metadata["has_signal"] else bundle_metadata

        proof_sentence = _clean_sentence(proof_artifact.get("sentence") or "")
        if (
            proof_sentence
            and active_metadata["has_signal"]
            and _contains_temporal_sequence_marker(proof_sentence)
        ):
            marker = proof_sentence.lower()
            if marker not in seen_support:
                seen_support.add(marker)
                support_lines.append(proof_sentence)

        unresolved_count = int(active_metadata.get("unresolved_count", 0) or 0)
        chronology_task_count = int(active_metadata.get("chronology_task_count", 0) or 0)
        if unresolved_count <= 0 and chronology_task_count <= 0:
            continue

        element_label = _clean_text(
            element.get("element_text") or element.get("element_id") or claim_name or claim_type
        ) or "This claim element"
        summary_parts: List[str] = []
        if unresolved_count > 0:
            summary_parts.append(f"{unresolved_count} unresolved chronology issue(s)")
        if chronology_task_count > 0:
            summary_parts.append(f"{chronology_task_count} chronology task(s)")
        objective_text = ""
        if active_metadata.get("proof_objectives"):
            objective_text = f" Focus on {str(active_metadata['proof_objectives'][0]).replace('_', ' ')}."
        summary = (
            f"{element_label} still carries {' and '.join(summary_parts)} in the proof handoff."
            f"{objective_text}"
        ).strip()
        marker = summary.lower()
        if marker in seen_hints:
            continue
        seen_hints.add(marker)
        gap_hints.append(
            {
                "name": "Chronology gap",
                "citation": "",
                "suggested_action": summary,
            }
        )

    return support_lines[:limit], gap_hints[:limit]
