"""Draft-text → Formal Logic → Theorem Prover pipeline.

Orchestrates the full proof pipeline for a complaint draft body:

    Step A  text_to_fol(body)              → FOL predicates
    Step B  legal_text_to_deontic(body)    → deontic norms
    Step C  constrain_assertions_to_corpus → ground assertions in legal corpus
    Step D  prove_claim_elements(preds)    → hybrid reasoner + Z3 prover
    Step E  check_policy_rules_with_deontic_norms → deontic violation check

The result is a :class:`DraftProofReport` (plain dict) that the workspace
injects into ``_build_mike_sync_diagnostics()`` via the ``logic_review``
parameter.

Additional utilities:

* :func:`render_proof_report` — render a ``DraftProofReport`` as a human-readable
  Markdown document suitable for display in the complaint editor or export.
* :func:`pin_proof_report_to_ipfs` — pin a ``DraftProofReport`` (plus its
  Lean 4 / Coq theorem exports) to IPFS for immutable provenance tracking.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .legal import constrain_assertions_to_corpus
from .logic import (
    legal_text_to_deontic,
    prove_claim_elements,
    text_to_fol,
)
from .policy_rules import check_policy_rules_with_deontic_norms

DRAFT_LOGIC_PIPELINE_VERSION = "draft-logic-pipeline-v1"


def _extract_text_assertions(body: str) -> List[Dict[str, Any]]:
    """Split *body* into per-sentence assertion dicts."""
    import re

    sentence_re = re.compile(r"(?<=[.!?])\s+|\n+")
    assertions: List[Dict[str, Any]] = []
    for index, sentence in enumerate(sentence_re.split(body), start=1):
        text = sentence.strip()
        if text:
            assertions.append({"assertion_id": f"sent-{index}", "text": text})
    return assertions


def _summarize_support_facts(support_facts: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    facts = [fact for fact in (support_facts or []) if isinstance(fact, dict)]
    source_family_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    parse_source_counts: Dict[str, int] = {}
    input_format_counts: Dict[str, int] = {}
    unique_fact_ids = set()
    unique_source_refs = set()
    passage_anchored_count = 0

    def _count(target: Dict[str, int], value: Any) -> None:
        text = str(value or "").strip()
        if text:
            target[text] = target.get(text, 0) + 1

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        if fact_id:
            unique_fact_ids.add(fact_id)
        source_ref = str(fact.get("source_ref") or "").strip()
        if source_ref:
            unique_source_refs.add(source_ref)
        source_passage = fact.get("source_passage") if isinstance(fact.get("source_passage"), dict) else {}
        if fact.get("chunk_id") or source_passage.get("chunk_id"):
            passage_anchored_count += 1

        _count(source_family_counts, fact.get("source_family"))
        _count(artifact_family_counts, fact.get("artifact_family"))
        _count(corpus_family_counts, fact.get("corpus_family"))
        _count(content_origin_counts, fact.get("content_origin"))
        _count(parse_source_counts, fact.get("parse_source"))
        _count(input_format_counts, fact.get("input_format"))

    return {
        "fact_count": len(facts),
        "unique_fact_count": len(unique_fact_ids),
        "unique_source_ref_count": len(unique_source_refs),
        "passage_anchored_count": passage_anchored_count,
        "source_family_counts": source_family_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
        "parse_source_counts": parse_source_counts,
        "input_format_counts": input_format_counts,
    }


def run_pipeline(
    body: str,
    *,
    state: Optional[str] = None,
    allow_live_scrape_fallback: bool = False,
    support_facts: Optional[List[Dict[str, Any]]] = None,
    fact_registry_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the full draft-logic pipeline on *body*.

    Parameters
    ----------
    body:
        The full draft complaint body text.
    state:
        Optional two-letter US state code used to narrow state-law corpus
        searches inside :func:`constrain_assertions_to_corpus`.
    allow_live_scrape_fallback:
        Whether to permit live-scrape calls for corpus searches.  Defaults to
        ``False`` so the pipeline stays fast in offline / test environments.

    Returns
    -------
    dict
        A ``DraftProofReport`` dict with the following keys:

        * ``proof_status`` — ``"passed"`` | ``"needs_review"`` | ``"error"``
        * ``contradiction_count`` — integer
        * ``chronology_blocked`` — bool
        * ``ungrounded_assertions`` — list of ungrounded assertion dicts
        * ``corpus_coverage_percent`` — int or None
        * ``norms`` — deontic norms extracted from the draft
        * ``policy_violations`` — list of deontic violation dicts
        * ``policy_warnings`` — list of deontic warning dicts
        * ``has_blockers`` — bool
        * ``pipeline_version`` — str
    """
    errors: List[str] = []
    normalized_fact_registry_summary = (
        dict(fact_registry_summary)
        if isinstance(fact_registry_summary, dict)
        else _summarize_support_facts(support_facts)
    )
    normalized_fact_registry_summary.setdefault("registry_version", "claim_fact_registry_summary.v1")
    normalized_fact_registry_summary.setdefault("source", "claim_support_facts")

    # ------------------------------------------------------------------
    # Step A — text → FOL predicates
    # ------------------------------------------------------------------
    fol_result: Dict[str, Any] = {}
    predicates: List[Dict[str, Any]] = []
    try:
        fol_result = text_to_fol(body)
        predicates = list(fol_result.get("predicates") or [])
    except Exception as exc:
        errors.append(f"text_to_fol: {exc}")

    # ------------------------------------------------------------------
    # Step B — legal text → deontic norms
    # ------------------------------------------------------------------
    deontic_result: Dict[str, Any] = {}
    norms: List[Dict[str, Any]] = []
    try:
        deontic_result = legal_text_to_deontic(body)
        norms = list(deontic_result.get("norms") or [])
    except Exception as exc:
        errors.append(f"legal_text_to_deontic: {exc}")

    # ------------------------------------------------------------------
    # Step C — constrain assertions to legal corpus
    # ------------------------------------------------------------------
    corpus_result: Dict[str, Any] = {}
    ungrounded_assertions: List[Dict[str, Any]] = []
    corpus_coverage_percent: Optional[int] = None
    try:
        assertions = _extract_text_assertions(body)
        corpus_result = constrain_assertions_to_corpus(
            assertions,
            state=state,
            allow_live_scrape_fallback=allow_live_scrape_fallback,
        )
        ungrounded_assertions = list(corpus_result.get("ungrounded") or [])
        corpus_coverage_percent = corpus_result.get("corpus_coverage_percent")
    except Exception as exc:
        errors.append(f"constrain_assertions_to_corpus: {exc}")

    # ------------------------------------------------------------------
    # Step D — prove claim elements via hybrid reasoner
    # ------------------------------------------------------------------
    proof_result: Dict[str, Any] = {}
    proof_status = "needs_review"
    contradiction_count = 0
    chronology_blocked = False
    theorem_export: Dict[str, Any] = {}
    try:
        proof_result = prove_claim_elements(predicates)
        proof_status = str(
            proof_result.get("proof_status")
            or (proof_result.get("proof_artifact") or {}).get("proof_status")
            or "needs_review"
        )
        contradiction_count = int(
            proof_result.get("contradiction_signal_count")
            or proof_result.get("contradiction_count")
            or 0
        )
        theorem_meta = dict(
            (proof_result.get("proof_artifact") or {}).get("theorem_export_metadata")
            or (proof_result.get("temporal_reasoning_payload") or {}).get("theorem_export_metadata")
            or {}
        )
        chronology_blocked = bool(theorem_meta.get("chronology_blocked"))
        # Carry through the Lean 4 / Coq export from prove_claim_elements.
        theorem_export = dict(proof_result.get("theorem_export") or {})
    except Exception as exc:
        errors.append(f"prove_claim_elements: {exc}")

    # ------------------------------------------------------------------
    # Step E — deontic policy rule check
    # ------------------------------------------------------------------
    policy_result: Dict[str, Any] = {}
    policy_violations: List[Dict[str, Any]] = []
    policy_warnings: List[Dict[str, Any]] = []
    try:
        policy_result = check_policy_rules_with_deontic_norms(body, norms=norms or None)
        policy_violations = list(policy_result.get("violations") or [])
        policy_warnings = list(policy_result.get("warnings") or [])
    except Exception as exc:
        errors.append(f"check_policy_rules_with_deontic_norms: {exc}")

    # ------------------------------------------------------------------
    # Assemble DraftProofReport
    # ------------------------------------------------------------------
    has_blockers = bool(
        contradiction_count
        or chronology_blocked
        or policy_violations
        or (proof_status in {"error", "failed", "violation"})
    )

    return {
        "proof_status": proof_status,
        "contradiction_count": contradiction_count,
        "chronology_blocked": chronology_blocked,
        "ungrounded_assertions": ungrounded_assertions,
        "ungrounded_assertion_count": len(ungrounded_assertions),
        "corpus_coverage_percent": corpus_coverage_percent,
        "norms": norms,
        "policy_violations": policy_violations,
        "policy_warnings": policy_warnings,
        "has_blockers": has_blockers,
        "predicate_count": len(predicates),
        "fact_registry_summary": normalized_fact_registry_summary,
        "theorem_export": theorem_export,
        "pipeline_version": DRAFT_LOGIC_PIPELINE_VERSION,
        "errors": errors,
        # Carry through sub-results for downstream consumers.
        "fol_result": fol_result,
        "deontic_result": deontic_result,
        "corpus_result": corpus_result,
        "proof_result": proof_result,
        "policy_result": policy_result,
    }


# ---------------------------------------------------------------------------
# Proof report renderer
# ---------------------------------------------------------------------------

def render_proof_report(
    report: Dict[str, Any],
    *,
    claim_id: str = "",
    rendered_at: Optional[str] = None,
) -> str:
    """Render a ``DraftProofReport`` as a human-readable Markdown document.

    Parameters
    ----------
    report:
        The dict returned by :func:`run_pipeline`.
    claim_id:
        Optional claim or case identifier embedded in the report header.
    rendered_at:
        ISO-8601 timestamp.  Defaults to the current UTC time.

    Returns
    -------
    str
        Markdown-formatted proof report suitable for display or export.
    """
    timestamp = rendered_at or datetime.now(tz=timezone.utc).isoformat()
    lines: List[str] = []

    # Header
    lines.append("# Complaint Draft Proof Report")
    if claim_id:
        lines.append(f"**Claim ID:** {claim_id}")
    lines.append(f"**Generated:** {timestamp}")
    lines.append(f"**Pipeline version:** {report.get('pipeline_version', DRAFT_LOGIC_PIPELINE_VERSION)}")
    lines.append("")

    # Status summary
    proof_status = str(report.get("proof_status") or "needs_review")
    status_icon = {"passed": "✅", "needs_review": "⚠️", "error": "❌", "failed": "❌"}.get(
        proof_status, "⚠️"
    )
    lines.append(f"## Status: {status_icon} `{proof_status}`")
    lines.append("")

    has_blockers = bool(report.get("has_blockers"))
    if has_blockers:
        lines.append("> **⛔ This draft has blockers that must be resolved before filing.**")
    else:
        lines.append("> **✔ No blockers found.  Draft may proceed.**")
    lines.append("")

    # Key metrics
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Predicates extracted | {report.get('predicate_count', 0)} |")
    contradiction_count = int(report.get("contradiction_count") or 0)
    lines.append(f"| Contradictions | {contradiction_count} |")
    chronology_blocked = bool(report.get("chronology_blocked"))
    lines.append(f"| Chronology blocked | {'Yes' if chronology_blocked else 'No'} |")
    coverage = report.get("corpus_coverage_percent")
    lines.append(f"| Corpus coverage | {f'{coverage}%' if coverage is not None else 'n/a'} |")
    fact_registry_summary = report.get("fact_registry_summary") if isinstance(report.get("fact_registry_summary"), dict) else {}
    lines.append(f"| Support facts | {int(fact_registry_summary.get('fact_count') or 0)} |")
    lines.append(f"| Passage-anchored facts | {int(fact_registry_summary.get('passage_anchored_count') or 0)} |")
    norms = list(report.get("norms") or [])
    lines.append(f"| Deontic norms found | {len(norms)} |")
    violations = list(report.get("policy_violations") or [])
    warnings = list(report.get("policy_warnings") or [])
    lines.append(f"| Policy violations | {len(violations)} |")
    lines.append(f"| Policy warnings | {len(warnings)} |")
    lines.append("")

    # Ungrounded assertions
    ungrounded = list(report.get("ungrounded_assertions") or [])
    if ungrounded:
        lines.append("## ⚠ Ungrounded Assertions")
        lines.append("")
        lines.append(
            "The following assertions could not be matched to any authoritative legal corpus document."
        )
        lines.append("Each must be grounded in a statute, regulation, or case before filing.")
        lines.append("")
        for item in ungrounded:
            assertion_id = str(item.get("assertion_id") or item.get("id") or "")
            text = str(item.get("text") or "").strip()
            prefix = f"**[{assertion_id}]** " if assertion_id else ""
            lines.append(f"- {prefix}{text}")
        lines.append("")

    # Contradictions
    if contradiction_count:
        lines.append("## ❌ Contradictions")
        lines.append("")
        proof_result = dict(report.get("proof_result") or {})
        contradiction_list = list(proof_result.get("contradictions") or [])
        if contradiction_list:
            for c in contradiction_list:
                cid = str(c.get("contradiction_id") or "")
                summary = str(c.get("summary") or "")
                severity = str(c.get("severity") or "warning")
                icon = "❌" if severity == "error" else "⚠️"
                lines.append(f"- {icon} **[{cid}]** {summary}")
        else:
            lines.append(f"- {contradiction_count} contradiction(s) detected.")
        lines.append("")

    # Policy violations
    if violations:
        lines.append("## ❌ Policy Violations")
        lines.append("")
        for v in violations:
            vtype = str(v.get("violation_type") or "violation")
            offending = str(v.get("offending_sentence") or "").strip()
            lines.append(f"- **{vtype}**: _{offending}_")
        lines.append("")

    # Policy warnings
    if warnings:
        lines.append("## ⚠ Policy Warnings")
        lines.append("")
        for w in warnings:
            wtype = str(w.get("warning_type") or "warning")
            formula = str(w.get("formula") or "").strip()
            suffix = f" (`{formula}`)" if formula else ""
            lines.append(f"- **{wtype}**{suffix}")
        lines.append("")

    # Deontic norms summary
    if norms:
        lines.append("## Deontic Norms Detected")
        lines.append("")
        for norm in norms:
            norm_type = str(norm.get("norm_type") or "").capitalize()
            formula = str(norm.get("formula") or "").strip()
            trigger = str(norm.get("trigger_keyword") or "").strip()
            detail = formula or trigger
            lines.append(f"- **{norm_type}**: `{detail}`")
        lines.append("")

    # Theorem export summary
    theorem_export = dict(report.get("theorem_export") or {})
    tdfol_count = int(theorem_export.get("tdfol_formula_count") or 0)
    dcec_count = int(theorem_export.get("dcec_formula_count") or 0)
    if tdfol_count or dcec_count:
        lines.append("## Theorem Export")
        lines.append("")
        lines.append(f"- TDFOL formulas: {tdfol_count}")
        lines.append(f"- DCEC formulas: {dcec_count}")
        export_version = str(theorem_export.get("export_version") or "")
        if export_version:
            lines.append(f"- Export version: `{export_version}`")
        lean4_present = bool(theorem_export.get("lean4"))
        coq_present = bool(theorem_export.get("coq"))
        if lean4_present:
            lines.append("- Lean 4 stub: available")
        if coq_present:
            lines.append("- Coq stub: available")
        lines.append("")

    # Pipeline errors
    errors = list(report.get("errors") or [])
    if errors:
        lines.append("## Pipeline Errors")
        lines.append("")
        for err in errors:
            lines.append(f"- `{err}`")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# IPFS provenance pinning
# ---------------------------------------------------------------------------

def pin_proof_report_to_ipfs(
    report: Dict[str, Any],
    *,
    claim_id: str = "",
) -> Dict[str, Any]:
    """Pin a ``DraftProofReport`` and its theorem exports to IPFS.

    Serialises the report as JSON and pins it via the workspace IPFS backend
    (``integrations.ipfs_datasets.storage``).  The Lean 4 and Coq theorem
    export strings are pinned as separate blobs so each artifact has its own
    CID.

    When the IPFS backend is unavailable (e.g. in offline / test
    environments) the function falls back gracefully to a local content-hash
    record without raising an exception.

    Parameters
    ----------
    report:
        The dict returned by :func:`run_pipeline`.
    claim_id:
        Optional claim identifier embedded in the pinned JSON envelope.

    Returns
    -------
    dict
        ``{"report_cid": str, "lean4_cid": str, "coq_cid": str,
           "pinned": bool, "backend": str, "pinned_at": str}``
    """
    from .storage import store_bytes, pin_cid, IPFS_AVAILABLE

    pinned_at = datetime.now(tz=timezone.utc).isoformat()
    backend = "ipfs" if IPFS_AVAILABLE else "local_content_hash"

    # Serialise the report envelope (exclude large sub-results to keep the
    # primary blob focused on the DraftProofReport keys).
    envelope: Dict[str, Any] = {
        "claim_id": claim_id,
        "pinned_at": pinned_at,
        "pipeline_version": report.get("pipeline_version", DRAFT_LOGIC_PIPELINE_VERSION),
        "proof_status": report.get("proof_status"),
        "contradiction_count": report.get("contradiction_count"),
        "chronology_blocked": report.get("chronology_blocked"),
        "corpus_coverage_percent": report.get("corpus_coverage_percent"),
        "ungrounded_assertion_count": report.get("ungrounded_assertion_count"),
        "has_blockers": report.get("has_blockers"),
        "predicate_count": report.get("predicate_count"),
        "policy_violation_count": len(list(report.get("policy_violations") or [])),
        "policy_warning_count": len(list(report.get("policy_warnings") or [])),
        "norm_count": len(list(report.get("norms") or [])),
        "errors": list(report.get("errors") or []),
    }

    theorem_export = dict(report.get("theorem_export") or {})
    lean4_src = str(theorem_export.get("lean4") or "")
    coq_src = str(theorem_export.get("coq") or "")

    def _pin_blob(data: bytes, description: str) -> str:
        import hashlib
        try:
            result = store_bytes(data)
            cid = str(
                (result.get("cid") if isinstance(result, dict) else result) or ""
            ).strip()
            if cid:
                try:
                    pin_cid(cid)
                except Exception:
                    pass
                return cid
        except Exception:
            pass
        # IPFS unavailable or returned an empty CID — fall back to a local
        # content-addressed hash so callers always get a non-empty identifier.
        return "sha256:" + hashlib.sha256(data).hexdigest()

    report_bytes = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
    report_cid = _pin_blob(report_bytes, "DraftProofReport")
    lean4_cid = _pin_blob(lean4_src.encode("utf-8"), "Lean4Export") if lean4_src else ""
    coq_cid = _pin_blob(coq_src.encode("utf-8"), "CoqExport") if coq_src else ""

    return {
        "report_cid": report_cid,
        "lean4_cid": lean4_cid,
        "coq_cid": coq_cid,
        "pinned": bool(report_cid),
        "backend": backend,
        "pinned_at": pinned_at,
        "claim_id": claim_id,
    }


__all__ = [
    "DRAFT_LOGIC_PIPELINE_VERSION",
    "run_pipeline",
    "render_proof_report",
    "pin_proof_report_to_ipfs",
]
