"""Bounded legal corpus lookup moved out of the datasets legal owner.

The moved callables keep the owner module globals so corpus caps, family
tokens, and retrieval helpers stay one object.
"""

from __future__ import annotations

import math

def build_bounded_legal_acquisition_request(
    legal_context: Optional[Mapping[str, Any]],
    claim_candidates: Optional[Iterable[Any]],
    *,
    requirements: Optional[Iterable[Any]] = None,
    query_terms: Optional[Iterable[Any]] = None,
    narrative: Any = None,
    authority_families: Optional[Iterable[Any]] = None,
    jurisdiction_default: Any = None,
    corpus_default: Any = None,
    max_results: int = 5,
    timeout_seconds: float = 5.0,
    storage_available: Optional[bool] = None,
    context_questions: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Bind a citation fetch to explicit jurisdiction, law date, and claims.

    A missing, ambiguous, or uncertain gate returns a targeted inquiry. This
    function does not choose Oregon, federal law, or a corpus, and it does not
    copy a law-query date into the factual chronology. The raw case narrative
    is not stored on the request and is not required to name a public-law query.
    """
    source = dict(legal_context) if isinstance(legal_context, Mapping) else empty_legal_context()
    if "jurisdiction" in source:
        source["jurisdiction"] = _explicit_jurisdiction_token(source.get("jurisdiction"))
    selection = intake_legal_selection(source, claim_candidates)
    jurisdiction = str(selection.get("jurisdiction") or UNKNOWN_LEGAL_CONTEXT)
    applicable = _classified_role(source, DATE_ROLE_APPLICABLE_LAW)
    event_date = _classified_role(source, DATE_ROLE_EVENT)
    filing_date = _classified_role(source, DATE_ROLE_FILING_REFERENCE)
    retrieval_date = _classified_role(source, DATE_ROLE_CORPUS_RETRIEVAL)
    law_query_date = applicable.get("precise_date") if _resolved_legal_date(applicable) else None
    event_resolved = _resolved_legal_date(event_date)
    chronology_gap = not event_resolved

    supported: List[Dict[str, Any]] = []
    unsupported: List[str] = []
    for item in selection.get("claim_candidates") or []:
        if not isinstance(item, Mapping):
            continue
        record = _supported_claim_record(item)
        if record is None:
            label = _text(item.get("claim_type") or item.get("name")) or "unspecified"
            if label not in unsupported:
                unsupported.append(label)
            continue
        supported.append(record)
    for item in claim_candidates or []:
        if isinstance(item, str):
            probe = {"claim_type": item}
        elif isinstance(item, Mapping):
            probe = item
        else:
            continue
        if _supported_claim_record(probe) is None:
            label = _text(probe.get("claim_type") if isinstance(probe, Mapping) else probe) or "unspecified"
            if label and label.lower() != "unknown" and label not in unsupported:
                unsupported.append(label)

    requirement_targets: List[Dict[str, str]] = []
    requirement_terms: List[str] = []
    supported_types = {item["claim_type"] for item in supported}
    explicit_requirements = list(requirements or [])
    for item in explicit_requirements:
        if not isinstance(item, Mapping):
            continue
        claim_type = _text(item.get("claim_type") or item.get("type"))
        supported_record = _supported_claim_record({"claim_type": claim_type}) if claim_type else None
        normalized = supported_record["claim_type"] if supported_record else ""
        if not normalized or normalized not in supported_types:
            label = claim_type or "unspecified"
            if label not in unsupported:
                unsupported.append(label)
            continue
        requirement_id = _text(item.get("requirement_id") or item.get("element_id") or item.get("name"))
        if not requirement_id:
            continue
        requirement_targets.append({
            "claim_type": normalized,
            "requirement_id": requirement_id,
            "label": _text(item.get("label") or item.get("name") or requirement_id),
            "target_kind": "caller_requirement",
        })
        requirement_terms.extend([
            _text(item.get("citation")),
            _text(item.get("public_query") or item.get("query")),
            _text(item.get("label") or item.get("name")),
        ])
    if not requirement_targets:
        for claim in supported:
            for element in claim["requirement_elements"]:
                requirement_targets.append({
                    "claim_type": claim["claim_type"],
                    "requirement_id": element["requirement_id"],
                    "label": element["label"] or element["requirement_id"],
                    "target_kind": "claim_requirement",
                })
                if len(requirement_targets) >= _ACQUISITION_TARGET_CAP:
                    break
    requirement_targets = requirement_targets[:_ACQUISITION_TARGET_CAP]
    claim_targets = [
        {"claim_type": claim["claim_type"], "name": claim["name"], "target_kind": "claim"}
        for claim in supported[:_ACQUISITION_TARGET_CAP]
    ]
    claim_terms = [claim["name"] or claim["claim_type"].replace("_", " ") for claim in supported]
    public_terms = _public_query_terms(query_terms or [], requirement_terms, claim_terms, narrative=str(narrative or ""))

    reasons = list(selection.get("unresolved_reasons") or [])
    if applicable.get("raw_text") and not law_query_date and "uncertain_applicable_law_date" not in reasons:
        reasons = [("uncertain_applicable_law_date" if reason == "missing_applicable_law_date" else reason) for reason in reasons]
        if "uncertain_applicable_law_date" not in reasons:
            reasons.append("uncertain_applicable_law_date")
    if unsupported and not supported and "unsupported_claim" not in reasons:
        reasons.append("unsupported_claim")
    if supported and not public_terms and "missing_public_law_query_terms" not in reasons:
        reasons.append("missing_public_law_query_terms")
    ready = bool(selection.get("ready_to_select") and supported and law_query_date and public_terms and jurisdiction != UNKNOWN_LEGAL_CONTEXT)

    questions: List[Dict[str, Any]] = []
    seen_questions = set()

    def _add_question(item: Mapping[str, Any]) -> None:
        field = _text(item.get("field") or item.get("question_id"))
        reason = _text(item.get("reason"))
        prompt = _text(item.get("prompt") or item.get("question"))
        if not prompt:
            return
        key = (field, reason, prompt)
        if key in seen_questions:
            return
        seen_questions.add(key)
        questions.append({
            "question_id": _text(item.get("question_id")) or f"legal_acquisition.{field or 'context'}",
            "field": field,
            "prompt": prompt,
            "reason": reason,
        })

    if not ready:
        for item in selection.get("questions") or []:
            if isinstance(item, Mapping):
                copied = dict(item)
                if copied.get("reason") == "missing_applicable_law_date" and applicable.get("raw_text") and not law_query_date:
                    copied["reason"] = "uncertain_applicable_law_date"
                    copied["prompt"] = (
                        "Which exact day should select the version of the law? "
                        "An uncertain date or range is kept as stated and is not treated as that day."
                    )
                _add_question(copied)
        for item in context_questions or []:
            if isinstance(item, Mapping):
                _add_question(item)
        if supported and not public_terms:
            _add_question({
                "question_id": "legal_acquisition.query_terms",
                "field": "query_terms",
                "reason": "missing_public_law_query_terms",
                "prompt": "Which public-law terms should be used to fetch the citation? The case narrative is not used as the query.",
            })
    if unsupported:
        listed = ", ".join(unsupported)
        _add_question({
            "question_id": "legal_acquisition.claim_candidates",
            "field": "claim_candidates",
            "reason": "unsupported_claim",
            "prompt": (
                f"Which supported claim should be acquired? {listed} is not a selected supported claim, "
                "so no jurisdiction or corpus was chosen for it."
            ),
        })
    if chronology_gap:
        _add_question({
            "question_id": "legal_context.event_dates",
            "field": "event_date",
            "reason": "missing_event_dates",
            "prompt": (
                "What dates or date ranges are relevant to the events? "
                "The date used to select a version of the law does not fill this chronology gap."
            ),
        })

    try:
        bounded_results = max(1, min(int(max_results), _ACQUISITION_RESULT_CAP))
    except (TypeError, ValueError):
        bounded_results = 5
    try:
        bounded_timeout = max(0.1, min(float(timeout_seconds), _ACQUISITION_TIMEOUT_CAP_SECONDS))
    except (TypeError, ValueError):
        bounded_timeout = 5.0
    corpus_plan = _closed_corpus_plan(jurisdiction if ready else UNKNOWN_LEGAL_CONTEXT, authority_families if ready else None)
    if not ready:
        for flag in (
            "search_us_code",
            "search_federal_register",
            "search_state_laws",
            "search_state_administrative_rules",
            "search_case_law",
        ):
            corpus_plan[flag] = False
        corpus_plan["jurisdiction"] = UNKNOWN_LEGAL_CONTEXT if jurisdiction == UNKNOWN_LEGAL_CONTEXT else jurisdiction
        corpus_plan["state_code"] = ""
        corpus_plan["context_status"] = UNKNOWN_LEGAL_CONTEXT

    dates = {
        DATE_ROLE_EVENT: event_date,
        DATE_ROLE_APPLICABLE_LAW: applicable,
        DATE_ROLE_FILING_REFERENCE: filing_date,
        DATE_ROLE_CORPUS_RETRIEVAL: retrieval_date,
    }
    rejected_defaults = {}
    if _text(jurisdiction_default):
        rejected_defaults["jurisdiction_default"] = _text(jurisdiction_default)
    if _text(corpus_default):
        rejected_defaults["corpus_default"] = _text(corpus_default)

    if storage_available is False:
        execution_status = "unavailable"
    elif ready:
        execution_status = "not_executed"
    else:
        execution_status = "blocked"

    request = None
    if ready:
        families = list(corpus_plan.get("authority_families") or [])
        request = {
            "request_id": "acq:" + ":".join([jurisdiction, str(law_query_date), "+".join(claim["claim_type"] for claim in claim_targets)]),
            "jurisdiction": jurisdiction,
            "law_query_date": law_query_date,
            "dates": dates,
            "claim_targets": claim_targets,
            "requirement_targets": requirement_targets,
            "public_law_query_terms": public_terms,
            "program": {
                "program_type": "bounded_legal_acquisition",
                "query_text": " ".join(public_terms),
                "jurisdiction": jurisdiction,
                "authority_families": families,
                "retrieval_mode": RETRIEVAL_MODE_OFFLINE,
                "contains_private_facts": False,
            },
            "corpus_plan": corpus_plan,
            "bounds": {
                "max_results": bounded_results,
                "timeout_seconds": bounded_timeout,
                "max_query_terms": _ACQUISITION_QUERY_TERM_CAP,
                "max_targets": _ACQUISITION_TARGET_CAP,
            },
            "contains_private_narrative": False,
        }
    return {
        "ready": ready,
        "request": request,
        "questions": questions,
        "inquiry": questions,
        "jurisdiction": jurisdiction if ready or jurisdiction != UNKNOWN_LEGAL_CONTEXT else UNKNOWN_LEGAL_CONTEXT,
        "selection_status": selection.get("selection_status"),
        "unresolved_reasons": [] if ready else list(dict.fromkeys(reasons)),
        "unsupported_claims": unsupported,
        "dates": dates,
        "law_query_date": law_query_date,
        "factual_chronology_gap": chronology_gap,
        "law_query_date_satisfies_factual_chronology": False,
        "corpus_plan": corpus_plan,
        "rejected_defaults": rejected_defaults,
        "execution": {
            "attempted": False,
            "status": execution_status,
            "backend_invoked": False,
            "results_claimed": False,
            "results": None,
            "storage_available": storage_available,
        },
        "narrative_required": False,
        "contains_private_narrative": False,
    }


def constrain_assertions_to_corpus(
    assertions: List[Dict[str, Any]],
    *,
    state: Optional[str] = None,
    max_results_per_assertion: int = 3,
    allow_live_scrape_fallback: bool = False,
    legal_vector_index_dir: Optional[str] = None,
    legal_context: Optional[Dict[str, Any]] = None,
    retrieval_mode: str = "offline",
    offline_cache: Optional[Dict[str, Any]] = None,
    index_path: Optional[str] = None,
    timeout_seconds: float = 5.0,
) -> Dict[str, Any]:
    """Separate corpus retrieval from source verification, applicability, and entailment.

    A search hit, similarity score, citation string, extracted sentence, or URL
    is only a retrieved candidate. Source verification requires the identified
    passage and provenance checks. Applicability requires the case's explicit
    jurisdiction, applicable-law date, and court, plus a versioned rule mapping.
    Entailment stays ``unsupported`` until a bound prover result exists.
    Caller-supplied ``grounded`` / ``entailed`` labels are ignored. Corpus
    retrieval uses the LAW02 bounded adapter and preserves its typed failures.
    Offline/cache assets are explicit. The legacy live-scrape compatibility
    argument never enables unbounded retrieval or grants remote consent.

    Compatibility fields use conservative meanings:

    * ``grounded`` is true only when that assertion is source-verified,
      applicable, and entailed. It is not true merely because retrieval
      returned a hit, and false does not mean the allegation is false or that
      no law applies.
    * ``ungrounded`` lists assertions that are not in that proved state.
      Membership is not a finding of falsity or of no applicable law.
    * ``corpus_coverage_percent`` counts assertions with at least one retrieved
      candidate. ``corpus_coverage_semantics`` is ``retrieval_only``. It is not
      a proof rate.
    """
    import os

    _vector_index_dir: Optional[str] = (
        legal_vector_index_dir
        or os.environ.get(_LEGAL_VECTOR_INDEX_DIR_ENV, "").strip()
        or None
    )

    grounded: List[Dict[str, Any]] = []
    ungrounded: List[Dict[str, Any]] = []
    details: List[Dict[str, Any]] = []
    context = legal_context if isinstance(legal_context, dict) else {}
    explicit_jurisdiction = resolve_explicit_jurisdiction(
        context.get("jurisdiction") if "jurisdiction" in context else state
    )
    applicable_law_date = classify_legal_date(
        context.get("applicable_law_date") or context.get(DATE_ROLE_APPLICABLE_LAW),
        role=DATE_ROLE_APPLICABLE_LAW,
    )
    court = _court_text(context.get("court"))
    expected_version = _constraint_text(context.get("corpus_version") or context.get("expected_corpus_version"))

    for index, assertion in enumerate(assertions or []):
        if not isinstance(assertion, dict):
            assertion = {}
        assertion_id = str(assertion.get("assertion_id") or assertion.get("id") or f"a-{index + 1}")
        text = str(assertion.get("text") or "").strip()
        kind = _constraint_text(assertion.get("assertion_kind") or assertion.get("kind") or "unspecified").casefold()
        ignored_labels = [key for key in _CONSTRAINT_CALLER_LABELS if key in assertion]
        # LAW01 pins this early exit to a fixed record. Unknown jurisdiction is
        # not a retrieval result, a proof, or a finding that no law applies.
        if explicit_jurisdiction == UNKNOWN_LEGAL_CONTEXT:
            details.append({
                "assertion_id": assertion_id,
                "text": text,
                "grounded": False,
                "applicability": UNKNOWN_LEGAL_CONTEXT,
                "reason": "unresolved_legal_context",
                "corpus_hits": [],
            })
            unresolved = {
                **assertion,
                "grounded": False,
                "applicability": UNKNOWN_LEGAL_CONTEXT,
                "corpus_hits": [],
            }
            for label in _CONSTRAINT_CALLER_LABELS:
                if label in unresolved:
                    unresolved[label] = False
            ungrounded.append(unresolved)
            continue
        citation_recognition = _recognize_citations(text) if text else []
        attempts: List[Dict[str, Any]] = []
        collected: List[Dict[str, Any]] = []

        if not text:
            attempts.append({"backend": "corpus", "status": "skipped", "reason": "empty_assertion_text"})
        else:
            if explicit_jurisdiction == "federal":
                _invoke_constraint_backend(
                    "us_code",
                    lambda text=text: lookup_bounded_legal_corpus(
                        source_family=CORPUS_FAMILY_US_CODE, query=text, retrieval_mode=retrieval_mode,
                        jurisdiction=explicit_jurisdiction, max_results=max_results_per_assertion,
                        offline_cache=offline_cache, index_path=index_path, timeout_seconds=timeout_seconds),
                    attempts,
                    collected,
                )
                if not collected:
                    _invoke_constraint_backend(
                        "federal_register",
                        lambda text=text: lookup_bounded_legal_corpus(
                            source_family=CORPUS_FAMILY_FEDERAL_REGISTER, query=text, retrieval_mode=retrieval_mode,
                            jurisdiction=explicit_jurisdiction, max_results=max_results_per_assertion,
                            offline_cache=offline_cache, timeout_seconds=timeout_seconds),
                        attempts,
                        collected,
                    )
            else:
                _invoke_constraint_backend(
                    "state_laws",
                    lambda text=text: lookup_bounded_legal_corpus(
                        source_family=CORPUS_FAMILY_STATE_STATUTE, query=text, retrieval_mode=retrieval_mode,
                        state=explicit_jurisdiction, jurisdiction=explicit_jurisdiction,
                        max_results=max_results_per_assertion, offline_cache=offline_cache,
                        timeout_seconds=timeout_seconds),
                    attempts,
                    collected,
                )
            if not collected and _vector_index_dir:
                # Merely setting an index path cannot authorize query embedding
                # through an ambient provider or an unbounded local index read.
                attempts.append({"backend": "legal_vector_index", "status": "unavailable",
                                 "error_code": "owned_vector_lookup_unavailable"})

        classified_hits = [
            _classify_constraint_hit(
                hit,
                assertion_text=text,
                backend=str(hit.get("_constraint_backend") or ""),
                jurisdiction=explicit_jurisdiction,
                applicable_law_date=applicable_law_date,
                court=court,
                expected_version=expected_version,
            )
            for hit in collected[:max_results_per_assertion]
        ]
        retrieval = _constraint_retrieval_status(attempts, len(classified_hits))
        source_verified = any(item.get("source_verified") for item in classified_hits)
        applicable = any(item.get("applicable") for item in classified_hits)
        # No bound prover is integrated. Unsupported is not a proof of non-entailment.
        entails = False
        entailment = ENTAILMENT_PROVER_INTEGRATION
        legally_grounded = bool(source_verified and applicable and entails)
        if retrieval == "empty":
            retrieval_reason = "empty_success"
        elif retrieval == "timeout":
            retrieval_reason = "timeout"
        elif retrieval == "backend_error":
            retrieval_reason = "backend_error"
        elif retrieval == "unavailable":
            retrieval_reason = "backend_unavailable"
        elif retrieval == "partial":
            retrieval_reason = "partial_retrieval"
        elif retrieval == "candidate":
            retrieval_reason = "retrieved_candidate"
        else:
            retrieval_reason = str((attempts[0].get("reason") if attempts else "") or "unknown")
        detail = {
            "assertion_id": assertion_id,
            "text": text,
            "assertion_kind": kind,
            "retrieved_candidate": retrieval == "candidate" or retrieval == "partial",
            "source_verified": source_verified,
            "applicable": applicable,
            "applicability": "applicable" if applicable else UNKNOWN_LEGAL_CONTEXT,
            "entails": entails,
            "dispositions": {
                "retrieval": retrieval,
                "source_verification": "verified" if source_verified else ("unknown" if retrieval in {UNKNOWN_LEGAL_CONTEXT, "empty", "timeout", "backend_error", "unavailable"} and not classified_hits else "unverified"),
                "applicability": "applicable" if applicable else UNKNOWN_LEGAL_CONTEXT,
                "entailment": entailment,
            },
            "grounded": legally_grounded,
            "grounding_semantics": "source_verified_and_applicable_and_entailed",
            "fact_verified": False,
            "allegation_status": UNKNOWN_LEGAL_CONTEXT,
            "applicable_law_conclusion": "applicable" if applicable else UNKNOWN_LEGAL_CONTEXT,
            "entailment_reason": "no_bound_entailment_prover",
            "reason": retrieval_reason,
            "diagnostics": attempts,
            "ignored_caller_labels": ignored_labels,
            "citation_recognition": "regex_not_source_verification" if citation_recognition else "none",
            "citation_recognition_count": len(citation_recognition),
            "factual_assertion": kind in _FACTUAL_ASSERTION_KINDS,
            "fact_promotion": "refused",
            "no_applicable_law": False,
            "allegation_false": False,
            "corpus_hits": classified_hits,
        }
        mapped_conflict = any(
            item.get("applicability") == "not_applicable"
            and "no_versioned_rule_mapping" not in (item.get("disposition_reasons") or [])
            for item in classified_hits
        )
        if not applicable and mapped_conflict:
            detail["dispositions"]["applicability"] = "not_applicable"
        detail["applicability"] = detail["dispositions"]["applicability"]
        detail["applicable_law_conclusion"] = "applicable" if applicable else UNKNOWN_LEGAL_CONTEXT
        details.append(detail)
        carried = {
            **assertion,
            "grounded": legally_grounded,
            "retrieved_candidate": detail["retrieved_candidate"],
            "source_verified": source_verified,
            "applicable": applicable,
            "applicability": detail["applicability"],
            "entails": entails,
            "entailed": False,
            "fact_verified": False,
            "allegation_status": UNKNOWN_LEGAL_CONTEXT,
            "corpus_hits": classified_hits,
            "diagnostics": attempts,
        }
        for label in ("verified", "legal_grounding"):
            if label in carried:
                carried[label] = False
        if legally_grounded:
            grounded.append(carried)
        else:
            ungrounded.append(carried)

    total = len(assertions or [])
    candidate_count = sum(1 for item in details if item.get("retrieved_candidate"))
    source_verified_count = sum(1 for item in details if item.get("source_verified"))
    applicable_count = sum(1 for item in details if item.get("applicable"))
    entailed_count = sum(1 for item in details if item.get("entails"))
    grounded_count = len(grounded)
    corpus_coverage_percent = int(round((candidate_count / total) * 100)) if total else None

    return {
        "grounded": grounded,
        "ungrounded": ungrounded,
        "details": details,
        "grounded_count": grounded_count,
        "ungrounded_count": len(ungrounded),
        "candidate_count": candidate_count,
        "source_verified_count": source_verified_count,
        "applicable_count": applicable_count,
        "entailed_count": entailed_count,
        "total_assertion_count": total,
        "corpus_coverage_percent": corpus_coverage_percent,
        "corpus_coverage_semantics": "retrieval_only",
        "grounded_is_not_proof_shortcut": True,
        "compatibility": {
            "grounded_semantics": (
                "true only when source_verified, applicable, and entailed are all true; "
                "false does not mean the allegation is false or that no law applies"
            ),
            "ungrounded_semantics": "not_proved_not_false_allegation",
            "corpus_coverage_percent_semantics": "retrieval_only",
        },
        "entailment_prover": ENTAILMENT_PROVER_INTEGRATION,
        "jurisdiction": explicit_jurisdiction,
        "context_status": UNKNOWN_LEGAL_CONTEXT if explicit_jurisdiction == UNKNOWN_LEGAL_CONTEXT else "explicit",
        "selected_rule_applicability": UNKNOWN_LEGAL_CONTEXT,
        "fact_graph_mutated": False,
    }


def lookup_bounded_legal_corpus(
    *,
    source_family: str,
    query: str = "",
    retrieval_mode: str = "",
    jurisdiction: Optional[str] = None,
    state: Optional[str] = None,
    max_results: int = 5,
    timeout_seconds: float = 5.0,
    collection_name: Optional[str] = None,
    query_vector: Optional[List[float]] = None,
    index_path: Optional[str] = None,
    offline_cache: Optional[Dict[str, Any]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    live_backend: str = "corpus",
    titles: Optional[List[str]] = None,
    contains_private_facts: bool = True,
    privacy_policy_accepted: bool = False,
    court_jurisdiction: Optional[str] = None,
) -> Dict[str, Any]:
    """Look up legal corpus candidates without implicit setup, scrape, or jurisdiction.

    ``cache`` reads only ``offline_cache``. ``offline`` reads that cache and a
    caller-supplied local US Code JSONL index. ``live`` calls one verified
    parameter-dictionary corpus API, or the Federal Register keyword API when
    ``live_backend`` is ``direct``. Missing assets return a typed unavailable
    envelope. Request labels are not copied onto rows as proof of jurisdiction,
    applicability, or effective date.
    """
    family = str(source_family or "").strip()
    mode = str(retrieval_mode or "").strip().lower()
    if type(max_results) is not int or not 0 <= max_results <= _BOUNDED_RESULT_CAP:
        return _bounded_envelope(status="unavailable", family=family, retrieval_mode=mode,
            capability="invalid_result_limit", error_code="invalid_result_limit")
    bounded_results = max_results
    if type(contains_private_facts) is not bool or type(privacy_policy_accepted) is not bool:
        return _bounded_envelope(status="unavailable", family=family, retrieval_mode=mode,
            capability="invalid_privacy_policy", error_code="invalid_privacy_policy")
    if family not in BOUNDED_CORPUS_FAMILIES:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability="unknown_source_family",
            error_code="unknown_source_family",
            error_message="source_family is not a bounded corpus adapter",
        )
    if mode not in BOUNDED_RETRIEVAL_MODES:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability="retrieval_mode_required",
            error_code="retrieval_mode_required",
            error_message="retrieval_mode must be cache, offline, or live",
        )
    try:
        timeout_value = float(timeout_seconds)
    except (TypeError, ValueError):
        timeout_value = 0.0
    if not math.isfinite(timeout_value) or timeout_value <= 0 or timeout_value > _BOUNDED_TIMEOUT_CAP_SECONDS:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability="invalid_timeout",
            error_code="invalid_timeout",
            error_message="timeout_seconds must be within the owned deadline cap",
            timeout_seconds=timeout_value if math.isfinite(timeout_value) else None,
        )

    requested_jurisdiction = resolve_explicit_jurisdiction(jurisdiction)
    requested_state = _resolve_state_code(state) if state else ""
    if family in {CORPUS_FAMILY_STATE_STATUTE, CORPUS_FAMILY_STATE_ADMIN} and not requested_state:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability="explicit_state_required",
            error_code="explicit_state_required",
            error_message="state statute and administrative lookups require an explicit state",
            timeout_seconds=timeout_value,
        )
    court_scope = str(court_jurisdiction or "").strip().lower()
    if family == CORPUS_FAMILY_COURT_RULE:
        if court_scope not in {"federal", "state", "both"}:
            return _bounded_envelope(
                status="unavailable",
                family=family,
                retrieval_mode=mode,
                capability="court_jurisdiction_required",
                error_code="court_jurisdiction_required",
                error_message="court rules require jurisdiction federal, state, or both",
                timeout_seconds=timeout_value,
            )
        if court_scope == "state" and not requested_state:
            return _bounded_envelope(
                status="unavailable",
                family=family,
                retrieval_mode=mode,
                capability="explicit_state_required",
                error_code="explicit_state_required",
                error_message="state court rules require an explicit state",
                timeout_seconds=timeout_value,
            )

    cache_rows = None
    if isinstance(offline_cache, dict):
        cache_rows = offline_cache.get(
            _cache_key(family, query, requested_jurisdiction if requested_jurisdiction != UNKNOWN_LEGAL_CONTEXT else "", requested_state)
        )
    if mode == RETRIEVAL_MODE_CACHE:
        if not isinstance(offline_cache, dict):
            return _bounded_envelope(
                status="unavailable",
                family=family,
                retrieval_mode=mode,
                capability="offline_cache_missing",
                error_code="offline_cache_missing",
                error_message="cache lookup requires an explicit offline cache",
                timeout_seconds=timeout_value,
            )
        results = _normalize_cached_rows(
            cache_rows,
            family=family,
            retrieval_mode=mode,
            requested_jurisdiction=jurisdiction or "",
            requested_state=requested_state,
            max_results=bounded_results,
        )
        return _bounded_envelope(
            status="success" if results else "empty",
            family=family,
            retrieval_mode=mode,
            capability="offline_cache",
            timeout_seconds=timeout_value,
            attempted_backends=["offline_cache"],
            results=results,
        )

    if mode == RETRIEVAL_MODE_OFFLINE:
        if isinstance(cache_rows, list) and cache_rows:
            results = _normalize_cached_rows(
                cache_rows,
                family=family,
                retrieval_mode=mode,
                requested_jurisdiction=jurisdiction or "",
                requested_state=requested_state,
                max_results=bounded_results,
            )
            return _bounded_envelope(
                status="success" if results else "empty",
                family=family,
                retrieval_mode=mode,
                capability="offline_cache",
                timeout_seconds=timeout_value,
                attempted_backends=["offline_cache"],
                results=results,
            )
        if family == CORPUS_FAMILY_US_CODE:
            return _lookup_local_us_code(
                query=query,
                index_path=index_path,
                titles=titles,
                max_results=bounded_results,
                timeout_seconds=timeout_value,
            )
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability="offline_asset_missing",
            error_code="offline_asset_missing",
            error_message="no local cache or index is available for this family",
            timeout_seconds=timeout_value,
            attempted_backends=["offline_cache"],
        )

    vector_block = _vector_parameters_ready(
        query_vector=query_vector,
        collection_name=collection_name,
        contains_private_facts=contains_private_facts,
        privacy_policy_accepted=privacy_policy_accepted,
    )
    publication_filter = {}
    if start_date:
        publication_filter["start_date"] = str(start_date)
    if end_date:
        publication_filter["end_date"] = str(end_date)

    if family == CORPUS_FAMILY_FEDERAL_REGISTER and live_backend == "direct":
        if contains_private_facts and not privacy_policy_accepted:
            return _bounded_envelope(
                status="unavailable",
                family=family,
                retrieval_mode=mode,
                capability="privacy_policy_required",
                error_code="privacy_policy_required",
                error_message="live Federal Register search refuses private case facts without a privacy policy",
                timeout_seconds=timeout_value,
            )
        if _search_federal_register_async is None:
            return _bounded_envelope(
                status="unavailable",
                family=family,
                retrieval_mode=mode,
                capability="federal_register_direct_unavailable",
                error_code="backend_unavailable",
                error_message="Federal Register direct API is not importable",
                timeout_seconds=timeout_value,
            )

        direct_parameters = dict(keywords=query, start_date=start_date, end_date=end_date,
            limit=bounded_results, fetch_all=False, max_pages=1, request_timeout=timeout_value)

        return _finish_live_call(
            family=family,
            parameters=direct_parameters,
            timeout_seconds=timeout_value,
            backend="federal_register_direct",
            requested_jurisdiction=jurisdiction or "",
            requested_state=requested_state,
            max_results=bounded_results,
            publication_filter=publication_filter or None,
            extra={
                "date_filter_role": "publication",
                "date_filter_is_effective_date": False,
            },
        )

    if vector_block:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability=vector_block,
            error_code=vector_block,
            error_message="live corpus search was not started",
            timeout_seconds=timeout_value,
        )

    parameters: Dict[str, Any] = {
        "collection_name": str(collection_name),
        "query_vector": list(query_vector or []),
        "top_k": bounded_results,
        "auto_setup_venv": False,
        "chunk_lookup_enabled": False,
    }
    backend_name = ""
    if family == CORPUS_FAMILY_US_CODE:
        backend_name = "us_code_corpus"
        capability = "us_code_corpus_unavailable"
    elif family == CORPUS_FAMILY_STATE_STATUTE:
        backend_name = "state_statute_corpus"
        capability = "state_law_corpus_unavailable"
        parameters["state"] = requested_state
        parameters["hf_dataset_id"] = DEFAULT_STATE_LAWS_DATASET_ID
        parameters["hf_dataset_ids"] = [DEFAULT_STATE_LAWS_DATASET_ID]
        parameters["enrich_with_cases"] = False
    elif family == CORPUS_FAMILY_STATE_ADMIN:
        caller = _search_state_law_corpus_async
        backend_name = "state_admin_corpus"
        capability = "state_law_corpus_unavailable"
        parameters["state"] = requested_state
        parameters["hf_dataset_id"] = DEFAULT_STATE_ADMIN_RULES_DATASET_ID
        parameters["hf_dataset_ids"] = [DEFAULT_STATE_ADMIN_RULES_DATASET_ID]
        parameters["enrich_with_cases"] = False
    elif family == CORPUS_FAMILY_FEDERAL_REGISTER:
        backend_name = "federal_register_corpus"
        capability = "federal_register_corpus_unavailable"
    else:
        backend_name = "court_rules_corpus"
        capability = "court_rules_corpus_unavailable"
        parameters["jurisdiction"] = court_scope
        parameters["enrich_with_cases"] = False
        if court_scope == "state":
            parameters["state"] = requested_state

    if parameters.get("auto_setup_venv") is not False:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=mode,
            capability="setup_refused",
            error_code="setup_refused",
            timeout_seconds=timeout_value,
        )

    return _finish_live_call(
        family=family,
        parameters=parameters,
        timeout_seconds=timeout_value,
        backend=backend_name,
        requested_jurisdiction=jurisdiction or "",
        requested_state=requested_state,
        max_results=bounded_results,
        publication_filter=publication_filter or None,
        extra={"request_parameters": {key: value for key, value in parameters.items()
            if key in {"top_k", "auto_setup_venv", "chunk_lookup_enabled", "state", "hf_dataset_id", "hf_dataset_ids", "enrich_with_cases", "jurisdiction"}}},
    )


def handoff_acquired_legal_sources(
    acquisition: Any,
    legal_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Admit one selected edition for the explicit legal context.

    Overlapping or unknown versions stay unresolved. Retrieval time is kept
    and is not copied into the applicable-law day. Treatment rows from the
    canonical record and metadata stay attached. Two versions that share an
    authority id are not folded into one admitted source.
    """
    from integrations.ipfs_datasets.logic import (
        evaluate_temporal_requirement_applicability,
        requirement_treatment_support,
    )

    payload = acquisition if isinstance(acquisition, Mapping) else {}
    context = legal_context if isinstance(legal_context, Mapping) else {}
    applicable_day = _explicit_applicable_law_day(context)
    jurisdiction = resolve_explicit_jurisdiction(context.get("jurisdiction"))
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    base: Dict[str, Any] = {
        "stage": "acquired_source_handoff",
        "acquisition_status": str(payload.get("status") or "unavailable"),
        "admitted": [],
        "unresolved": [],
        "withheld": [],
        "proof": False,
        "applicable": False,
        "retrieval_time_used_as_applicable_law": False,
        "applicable_law_date": applicable_day,
        "worker_stalled": False,
        "mixed_authority_versions": False,
    }
    acquisition_status = base["acquisition_status"]
    if acquisition_status in {"cancelled", "unavailable", "timeout", "error", "blocked", "refused", "missing_edition", "incomplete"}:
        base["status"] = acquisition_status if acquisition_status != "blocked" else "unresolved"
        base["reason"] = str(payload.get("error_code") or acquisition_status)
        return base
    if not candidates:
        base["status"] = "empty" if acquisition_status in {"empty", "candidates"} else acquisition_status or "empty"
        base["reason"] = "no_legal_source" if base["status"] == "empty" else acquisition_status
        return base
    if jurisdiction == UNKNOWN_LEGAL_CONTEXT or not applicable_day:
        base["status"] = "unresolved"
        base["reason"] = "unknown_legal_context" if jurisdiction == UNKNOWN_LEGAL_CONTEXT else "unknown_applicable_law_date"
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                base["unresolved"].append({
                    "authority_id": _candidate_authority_id(candidate),
                    "version": str(candidate.get("version") or ""),
                    "reason": base["reason"],
                    "retrieved_at": (candidate.get("retrieval") or {}).get("retrieved_at") if isinstance(candidate.get("retrieval"), Mapping) else None,
                })
        return base

    grouped: Dict[str, List[tuple]] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            base["withheld"].append({"reason": "candidate_malformed"})
            continue
        rows = _candidate_version_rows(candidate)
        authority_id = rows[0]["authority_id"] if rows else ""
        grouped.setdefault(authority_id or f"missing:{index}", []).append((candidate, rows))

    for authority_id, items in grouped.items():
        flat = []
        for candidate, rows in items:
            for row in rows:
                flat.append((candidate, row))
        distinct = {}
        contradictory = False
        for candidate, row in flat:
            key = (row.get("authority_id") or authority_id, row.get("version") or "")
            prior = distinct.get(key)
            if prior is not None:
                if prior[1].get("source_text") and row.get("source_text") and prior[1]["source_text"] != row["source_text"]:
                    contradictory = True
                if prior[1].get("effective_date") and row.get("effective_date") and prior[1]["effective_date"] != row["effective_date"]:
                    contradictory = True
                continue
            distinct[key] = (candidate, row)
        versions = list(distinct.values())
        unknown = [row for _candidate, row in versions if not _version_known(str(row.get("version") or "")) or not row.get("effective_date")]
        overlaps = False
        for left_index, (_left_candidate, left) in enumerate(versions):
            for _right_candidate, right in versions[left_index + 1:]:
                if _intervals_overlap(left, right) or left.get("embedded_other_version") or right.get("embedded_other_version"):
                    overlaps = True
        shared = len(versions) > 1
        if shared:
            base["mixed_authority_versions"] = True
        if contradictory or unknown or overlaps or any(row.get("embedded_other_version") for _candidate, row in versions):
            reason = "overlapping_versions" if overlaps or any(row.get("embedded_other_version") for _candidate, row in versions) else "unknown_version" if unknown else "contradictory_versions"
            for candidate, row in versions:
                base["unresolved"].append({
                    "authority_id": row.get("authority_id") or authority_id,
                    "version": row.get("version") or "",
                    "law_version_id": row.get("law_version_id") or "",
                    "effective_date": row.get("effective_date") or "",
                    "end_date": row.get("end_date") or "",
                    "reason": reason,
                    "retrieved_at": row.get("retrieved_at"),
                    "applicable_law_date": applicable_day,
                    "edition_selected": False,
                    "treatment_records": retain_acquired_treatment_records(candidate),
                    "source_text": row.get("source_text") or "",
                })
            continue
        selected = [(candidate, row) for candidate, row in versions if _interval_contains(row, applicable_day)]
        if len(selected) != 1:
            reason = "edition_not_in_effect" if not selected else "overlapping_versions"
            for candidate, row in versions:
                base["unresolved"].append({
                    "authority_id": row.get("authority_id") or authority_id,
                    "version": row.get("version") or "",
                    "reason": reason,
                    "edition_selected": False,
                    "retrieved_at": row.get("retrieved_at"),
                    "applicable_law_date": applicable_day,
                    "treatment_records": retain_acquired_treatment_records(candidate),
                })
            continue
        candidate, row = selected[0]
        for _other, other in versions:
            if other is row:
                continue
            base["withheld"].append({
                "authority_id": other.get("authority_id") or authority_id,
                "version": other.get("version") or "",
                "reason": "edition_not_selected",
                "edition_selected": False,
            })
        treatments = retain_acquired_treatment_records(candidate)
        temporal_payload = {
            "authority_id": row.get("authority_id") or authority_id,
            "citation": row.get("citation") or candidate.get("locator") or "",
            "jurisdiction": jurisdiction,
            "authority_version": row.get("version") or "",
            "version": row.get("version") or "",
            "source_text": row.get("source_text") or "",
            "law_version_id": row.get("law_version_id") or "",
            "effective_date": row.get("effective_date") or "",
            "law_versions": [{
                "law_version_id": row.get("law_version_id") or "",
                "authority_id": row.get("authority_id") or authority_id,
                "citation": row.get("citation") or "",
                "jurisdiction": jurisdiction,
                "version": row.get("version") or "",
                "effective_date": row.get("effective_date") or "",
                **({"sunset_date": row.get("end_date")} if row.get("end_date") else {}),
            }],
            "authority_treatment_edges": treatments,
            "query_context": {
                "jurisdiction": jurisdiction,
                "query_date": applicable_day,
                "authority_version": row.get("version") or "",
                "law_version_id": row.get("law_version_id") or "",
            },
        }
        if row.get("end_date"):
            temporal_payload["sunset_date"] = row.get("end_date")
        temporal = evaluate_temporal_requirement_applicability(temporal_payload)
        treatment_support = requirement_treatment_support({"authority_treatment_edges": treatments})
        retrieved_at = row.get("retrieved_at")
        if isinstance(retrieved_at, str) and retrieved_at[:10] == applicable_day and "T" in retrieved_at:
            base["retrieval_time_used_as_applicable_law"] = False
        admitted = {
            "authority_id": row.get("authority_id") or authority_id,
            "authority_version": row.get("version") or "",
            "version": row.get("version") or "",
            "law_version_id": row.get("law_version_id") or "",
            "jurisdiction": jurisdiction,
            "citation": row.get("citation") or "",
            "locator": candidate.get("locator"),
            "source_text": row.get("source_text") or "",
            "effective_date": row.get("effective_date") or "",
            "end_date": row.get("end_date") or "",
            "applicable_law_date": applicable_day,
            "retrieved_at": retrieved_at,
            "edition_selected": False,
            "treatment_records": treatments,
            "authority_treatment_edges": treatments,
            "treatment_support": treatment_support,
            "temporal_applicability": temporal,
            "support_eligible": False,
            "applicable": False,
            "proof": False,
            "mixed_with_other_version": False,
        }
        if temporal.get("available") is not True:
            admitted["edition_selected"] = False
            base["unresolved"].append(dict(admitted, reason=str(temporal.get("reason") or "temporal_unavailable")))
            continue
        if temporal.get("applicable") is not True:
            admitted["edition_selected"] = False
            base["unresolved"].append(dict(admitted, reason=str(temporal.get("reason") or temporal.get("applicability_status") or "not_applicable")))
            continue
        blocking = bool(treatment_support.get("treatment_blocks_support")) or any(
            item.get("adverse_treatment_retained") for item in treatments
        )
        admitted["edition_selected"] = True
        admitted["applicable"] = True
        admitted["support_eligible"] = not blocking
        admitted["treatment_blocks_support"] = blocking
        base["admitted"].append(admitted)

    if any(item.get("reason") == "temporal_authority_api_unavailable" or str(item.get("temporal_applicability", {}).get("reason") if isinstance(item.get("temporal_applicability"), Mapping) else "") == "temporal_authority_api_unavailable" for item in base["unresolved"]):
        temporal_down = [item for item in base["unresolved"] if "temporal" in str(item.get("reason") or "")]
        if temporal_down and not base["admitted"] and len(temporal_down) == len(base["unresolved"]):
            base["status"] = "unavailable"
            base["reason"] = "temporal_authority_api_unavailable"
            return base
    if base["admitted"] and not base["unresolved"]:
        base["status"] = "admitted"
        base["reason"] = "selected_edition"
    elif base["admitted"]:
        base["status"] = "partial"
        base["reason"] = "partial_edition_selection"
    elif base["unresolved"]:
        base["status"] = "unresolved"
        base["reason"] = str(base["unresolved"][0].get("reason") or "unresolved")
    else:
        base["status"] = "empty"
        base["reason"] = "no_legal_source"
    base["retrieval_time_used_as_applicable_law"] = False
    for item in base["admitted"] + base["unresolved"]:
        if item.get("retrieved_at") and item.get("applicable_law_date") and item.get("retrieved_at") == item.get("applicable_law_date"):
            base["retrieval_time_used_as_applicable_law"] = True
        if item.get("effective_date") and item.get("retrieved_at") and item.get("effective_date") == item.get("retrieved_at") and "T" not in str(item.get("retrieved_at")):
            pass
    return base

from .legal import (
    BOUNDED_CORPUS_FAMILIES,
    BOUNDED_RETRIEVAL_MODES,
    CORPUS_FAMILY_COURT_RULE,
    CORPUS_FAMILY_FEDERAL_REGISTER,
    CORPUS_FAMILY_STATE_ADMIN,
    CORPUS_FAMILY_STATE_STATUTE,
    CORPUS_FAMILY_US_CODE,
    DATE_ROLE_APPLICABLE_LAW,
    DATE_ROLE_CORPUS_RETRIEVAL,
    DATE_ROLE_EVENT,
    DATE_ROLE_FILING_REFERENCE,
    DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
    DEFAULT_STATE_LAWS_DATASET_ID,
    ENTAILMENT_PROVER_INTEGRATION,
    RETRIEVAL_MODE_CACHE,
    RETRIEVAL_MODE_OFFLINE,
    UNKNOWN_LEGAL_CONTEXT,
    _ACQUISITION_QUERY_TERM_CAP,
    _ACQUISITION_RESULT_CAP,
    _ACQUISITION_TARGET_CAP,
    _ACQUISITION_TIMEOUT_CAP_SECONDS,
    _BOUNDED_RESULT_CAP,
    _BOUNDED_TIMEOUT_CAP_SECONDS,
    _CONSTRAINT_CALLER_LABELS,
    _FACTUAL_ASSERTION_KINDS,
    _LEGAL_VECTOR_INDEX_DIR_ENV,
    _bounded_envelope,
    _cache_key,
    _candidate_authority_id,
    _candidate_version_rows,
    _classified_role,
    _classify_constraint_hit,
    _closed_corpus_plan,
    _constraint_retrieval_status,
    _constraint_text,
    _court_text,
    _explicit_applicable_law_day,
    _explicit_jurisdiction_token,
    _finish_live_call,
    _interval_contains,
    _intervals_overlap,
    _invoke_constraint_backend,
    _lookup_local_us_code,
    _normalize_cached_rows,
    _public_query_terms,
    _recognize_citations,
    _resolve_state_code,
    _resolved_legal_date,
    _search_federal_register_async,
    _search_state_law_corpus_async,
    _supported_claim_record,
    _text,
    _vector_parameters_ready,
    _version_known,
    classify_legal_date,
    empty_legal_context,
    intake_legal_selection,
    resolve_explicit_jurisdiction,
    retain_acquired_treatment_records,
)
