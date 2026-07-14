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
"""

from __future__ import annotations

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


def run_pipeline(
    body: str,
    *,
    state: Optional[str] = None,
    allow_live_scrape_fallback: bool = False,
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


__all__ = [
    "DRAFT_LOGIC_PIPELINE_VERSION",
    "run_pipeline",
]
