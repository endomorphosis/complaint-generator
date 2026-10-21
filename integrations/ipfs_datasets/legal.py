from __future__ import annotations

import calendar
import logging
import re
from typing import Any, Dict, List, Optional

from .loader import import_attr_optional, run_async_compat
from .types import with_adapter_metadata
from .vector_store import EMBEDDINGS_AVAILABLE, embed_text as embed_query_text, get_embeddings_router


logger = logging.getLogger(__name__)

DEFAULT_LEGAL_QUERY_EMBEDDING_MODEL = "thenlper/gte-small"
DEFAULT_STATE_LAWS_DATASET_ID = "justicedao/ipfs_state_laws"
DEFAULT_STATE_ADMIN_RULES_DATASET_ID = "justicedao/ipfs_state_admin_rules"
DEFAULT_FEDERAL_REGISTER_DATASET_ID = "justicedao/ipfs_federal_register"
_LAST_LEGAL_SEARCH_DIAGNOSTICS: Dict[str, Dict[str, Any]] = {}


def _set_last_legal_search_diagnostic(search_key: str, diagnostic: Optional[Dict[str, Any]]) -> None:
    if not search_key:
        return
    if diagnostic:
        _LAST_LEGAL_SEARCH_DIAGNOSTICS[search_key] = dict(diagnostic)
    else:
        _LAST_LEGAL_SEARCH_DIAGNOSTICS.pop(search_key, None)


def get_last_legal_search_diagnostic(search_key: str) -> Dict[str, Any]:
    if not search_key:
        return {}
    return dict(_LAST_LEGAL_SEARCH_DIAGNOSTICS.get(search_key) or {})


def _build_hf_search_diagnostic(
    *,
    search_key: str,
    query: str,
    state_code: Optional[str],
    hf_dataset_id: str,
    preferred_files: List[str],
) -> Dict[str, Any]:
    return {
        "search_key": search_key,
        "query": str(query or ""),
        "state_code": str(state_code or "").upper(),
        "hf_dataset_id": hf_dataset_id,
        "preferred_files": list(preferred_files),
        "attempted_backends": [],
        "warning_code": "",
        "warning_message": "",
        "parquet": {
            "attempted_files": [],
        },
    }


def _set_hf_search_warning(
    diagnostics: Optional[Dict[str, Any]],
    *,
    warning_code: str,
    warning_message: str,
) -> None:
    if not diagnostics:
        return
    if diagnostics.get("warning_code"):
        return
    diagnostics["warning_code"] = warning_code
    diagnostics["warning_message"] = warning_message


def _coerce_vector_payload(vector: Any) -> List[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    if isinstance(vector, tuple):
        vector = list(vector)
    if not isinstance(vector, list):
        raise TypeError("query embedding must be a list-like vector")
    return [float(value) for value in vector]


def _build_query_vector(
    query: str,
    *,
    model_name: str = DEFAULT_LEGAL_QUERY_EMBEDDING_MODEL,
    provider: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[float] | None:
    query_text = str(query or "").strip()
    if not query_text or not EMBEDDINGS_AVAILABLE:
        return None

    if callable(embed_query_text):
        try:
            return _coerce_vector_payload(
                embed_query_text(
                    query_text,
                    model_name=model_name,
                    provider=provider,
                )
            )
        except Exception as exc:
            # The router below is an intentional compatibility fallback, but a
            # failed direct provider call must remain observable. In
            # particular, otherwise-invalid provider output was previously
            # indistinguishable from an unavailable embeddings backend.
            if diagnostics is not None:
                diagnostics["direct_embedding_failure"] = {
                    "backend": "embed_text",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "fallback": "embeddings_router",
                }
            logger.warning(
                "Direct legal query embedding failed; falling back to the embeddings router",
                exc_info=True,
            )

    router = None
    try:
        router = get_embeddings_router(provider=provider, model_name=model_name)
    except Exception:
        router = None

    if router is None or not callable(getattr(router, "embed_text", None)):
        return None

    try:
        return _coerce_vector_payload(router.embed_text(query_text))
    except Exception as exc:
        embedding_diagnostic = {
            "status": "error",
            "stage": "router_embed_text",
            "provider": str(provider or "auto"),
            "model_name": str(model_name or ""),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        if diagnostics is not None:
            diagnostics["embedding"] = embedding_diagnostic
        logger.warning(
            "Legal query embedding failed; continuing with text-search fallbacks "
            "(provider=%s, model=%s, error_type=%s)",
            embedding_diagnostic["provider"],
            embedding_diagnostic["model_name"],
            embedding_diagnostic["error_type"],
            exc_info=True,
        )
        return None


def _import_attr_from_candidates(module_names: List[str], attr_name: str) -> tuple[Any | None, Any | None]:
    first_error: Any | None = None
    for module_name in module_names:
        value, error = import_attr_optional(module_name, attr_name)
        if value is not None:
            return value, None
        if first_error is None and error is not None:
            first_error = error
    return None, first_error


_search_us_code_async, _us_code_error = _import_attr_from_candidates(
    [
        "ipfs_datasets_py.processors.legal_scrapers.us_code_scraper",
        "ipfs_datasets_py.processors.legal_scrapers.federal_scrapers.us_code_scraper",
    ],
    "search_us_code",
)
_search_federal_register_async, _federal_register_error = _import_attr_from_candidates(
    [
        "ipfs_datasets_py.processors.legal_scrapers.federal_register_scraper",
        "ipfs_datasets_py.processors.legal_scrapers.federal_scrapers.federal_register_scraper",
    ],
    "search_federal_register",
)
_search_recap_documents_async, _recap_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.recap_archive_scraper",
    "search_recap_documents",
)
_search_federal_register_hf_index_async, _federal_register_hf_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
    "search_federal_register_hf_index_from_parameters",
)
_search_state_law_corpus_async, _state_law_corpus_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
    "search_state_law_corpus_from_parameters",
)
_scrape_state_laws_async, _state_laws_scrape_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
    "scrape_state_laws_from_parameters",
)
_scrape_state_admin_rules_async, _state_admin_rules_scrape_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api",
    "scrape_state_admin_rules_from_parameters",
)
_state_code_map, _state_code_map_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.state_laws_scraper",
    "US_STATES",
)
# Live IPFS streaming backend — optional; available when ipfs_datasets_py
# exposes the state_laws IPFS-streaming dataset adapter.
_stream_ipfs_state_laws_async, _ipfs_stream_state_laws_error = import_attr_optional(
    "ipfs_datasets_py.datasets.state_laws_ipfs_stream",
    "stream_state_laws_from_ipfs",
)


# Explicit state names. Unrecognized or missing text stays unresolved.
_EXPLICIT_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
_FEDERAL_JURISDICTION_TOKENS = {
    "federal",
    "federal court",
    "federal law",
    "us",
    "u.s.",
    "u.s",
    "united states",
    "united states of america",
}
UNKNOWN_LEGAL_CONTEXT = "unknown"
DATE_ROLE_APPLICABLE_LAW = "applicable_law_date"
DATE_ROLE_EVENT = "event_date"
DATE_ROLE_FILING_REFERENCE = "filing_reference_date"
DATE_ROLE_CORPUS_RETRIEVAL = "corpus_retrieval_date"
LEGAL_DATE_ROLES = (
    DATE_ROLE_APPLICABLE_LAW,
    DATE_ROLE_EVENT,
    DATE_ROLE_FILING_REFERENCE,
    DATE_ROLE_CORPUS_RETRIEVAL,
)
_MONTH_NAME_TO_NUMBER = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_UNCERTAIN_DATE_RE = re.compile(
    r"\b(?:about|around|approximately|approx\.?|sometime|some time|early|late|mid|"
    r"spring|summer|fall|autumn|winter|unclear|roughly)\b",
    re.IGNORECASE,
)
def _resolve_state_code(value: Optional[str], *, default: Optional[str] = None) -> str:
    """Resolve an explicit state code.

    Missing and unrecognized values stay unresolved. Callers must pass ``default``
    themselves; Oregon is never implied.
    """
    state = str(value or "").strip()
    fallback = str(default or "").strip().upper()
    if not state:
        return fallback
    if len(state) == 2 and state.isalpha():
        code = state.upper()
        if code in {"US", "FD"}:
            return fallback
        return code
    state_map = dict(_EXPLICIT_STATE_NAMES)
    if isinstance(_state_code_map, dict):
        for code, name in _state_code_map.items():
            label = str(name or "").strip().lower()
            if label:
                state_map.setdefault(label, str(code).upper())
    lowered = state.lower()
    if lowered in state_map:
        return state_map[lowered]
    return fallback


def resolve_explicit_jurisdiction(value: Optional[str]) -> str:
    """Return a jurisdiction only when the caller stated one.

    Unresolved text stays ``unknown``. Federal law is selected only from an
    explicit federal or United States token, never as a fallback.
    """
    text = " ".join(str(value or "").split())
    if not text:
        return UNKNOWN_LEGAL_CONTEXT
    lowered = text.lower().rstrip(".")
    if lowered in _FEDERAL_JURISDICTION_TOKENS:
        return "federal"
    state_code = _resolve_state_code(text)
    if state_code:
        return state_code
    return UNKNOWN_LEGAL_CONTEXT


def _calendar_month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _parse_explicit_legal_date(value: str) -> Dict[str, Any]:
    """Parse a date the user actually stated. Uncertain wording stays a range."""
    raw = " ".join(str(value or "").split())
    parsed: Dict[str, Any] = {
        "raw_text": raw,
        "precise_date": None,
        "start_date": None,
        "end_date": None,
        "granularity": "unknown",
        "precision": "unknown",
        "is_range": False,
        "is_uncertain": False,
    }
    if not raw:
        parsed["is_uncertain"] = True
        return parsed
    if _UNCERTAIN_DATE_RE.search(raw):
        parsed.update({
            "granularity": "uncertain_range",
            "precision": "uncertain_range",
            "is_range": True,
            "is_uncertain": True,
        })
        return parsed

    month_names = "|".join(_MONTH_NAME_TO_NUMBER)
    range_match = re.search(
        rf"\b(?:from\s+)?(.+?)\s+(?:to|through|until|-)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if range_match and range_match.group(1).strip() and range_match.group(2).strip():
        start = _parse_explicit_legal_date(range_match.group(1).strip())
        end = _parse_explicit_legal_date(range_match.group(2).strip())
        if start.get("precision") != "unknown" or end.get("precision") != "unknown":
            parsed.update({
                "start_date": start.get("start_date") or start.get("precise_date"),
                "end_date": end.get("end_date") or end.get("precise_date"),
                "granularity": "range",
                "precision": "range",
                "is_range": True,
                "is_uncertain": bool(start.get("is_uncertain") or end.get("is_uncertain")),
            })
            return parsed

    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if iso_match:
        year, month, day = (int(item) for item in iso_match.groups())
        iso_date = f"{year:04d}-{month:02d}-{day:02d}"
        parsed.update({
            "precise_date": iso_date,
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "precision": "day",
        })
        return parsed

    month_day_year = re.search(
        rf"\b({month_names})\s+(\d{{1,2}}),\s*(\d{{4}})\b",
        raw,
        flags=re.IGNORECASE,
    )
    if month_day_year:
        month = _MONTH_NAME_TO_NUMBER[month_day_year.group(1).lower()]
        day = int(month_day_year.group(2))
        year = int(month_day_year.group(3))
        iso_date = f"{year:04d}-{month:02d}-{day:02d}"
        parsed.update({
            "precise_date": iso_date,
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "precision": "day",
        })
        return parsed

    month_year = re.search(rf"\b({month_names})\s+(\d{{4}})\b", raw, flags=re.IGNORECASE)
    if month_year:
        month = _MONTH_NAME_TO_NUMBER[month_year.group(1).lower()]
        year = int(month_year.group(2))
        start_date, end_date = _calendar_month_bounds(year, month)
        parsed.update({
            "start_date": start_date,
            "end_date": end_date,
            "granularity": "month",
            "precision": "month",
            "is_range": True,
        })
        return parsed

    year_match = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", raw)
    if year_match:
        year = int(year_match.group(1))
        parsed.update({
            "start_date": f"{year:04d}-01-01",
            "end_date": f"{year:04d}-12-31",
            "granularity": "year",
            "precision": "year",
            "is_range": True,
        })
        return parsed
    return parsed


def classify_legal_date(value: Any, *, role: str) -> Dict[str, Any]:
    """Classify one legal date role without collapsing other roles into it."""
    if role not in LEGAL_DATE_ROLES:
        raise ValueError(f"unsupported legal date role: {role}")
    if isinstance(value, dict) and str(value.get("role") or "") == role:
        raw_value = value.get("raw_text")
    else:
        raw_value = value
    classified = _parse_explicit_legal_date(str(raw_value or ""))
    classified["role"] = role
    return classified


def empty_legal_context() -> Dict[str, Any]:
    """Legal context before the user supplies jurisdiction or dates."""
    return {
        "status": UNKNOWN_LEGAL_CONTEXT,
        "jurisdiction": UNKNOWN_LEGAL_CONTEXT,
        "jurisdiction_explicit": False,
        "applicable_law_date": classify_legal_date("", role=DATE_ROLE_APPLICABLE_LAW),
        "event_date": classify_legal_date("", role=DATE_ROLE_EVENT),
        "event_dates": [],
        "filing_reference_date": classify_legal_date("", role=DATE_ROLE_FILING_REFERENCE),
        "corpus_retrieval_date": classify_legal_date("", role=DATE_ROLE_CORPUS_RETRIEVAL),
        "selected_rule_applicability": UNKNOWN_LEGAL_CONTEXT,
        "proof_state": UNKNOWN_LEGAL_CONTEXT,
        "dependent_proof": [],
        "context_revision": 0,
        "changed_fields": [],
        "questions": [],
    }


def _date_raw(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    return " ".join(str(record.get("raw_text") or "").split())


def apply_legal_context_update(
    previous: Optional[Dict[str, Any]],
    updates: Optional[Dict[str, Any]] = None,
    *,
    dependent_proof: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Merge explicit context. A real change invalidates old rule and proof state."""
    current = dict(previous or empty_legal_context())
    if not isinstance(current.get("applicable_law_date"), dict):
        current = empty_legal_context()
    proposed = dict(updates or {})
    changed: List[str] = []

    if "jurisdiction" in proposed:
        resolved = resolve_explicit_jurisdiction(proposed.get("jurisdiction"))
        prior = str(current.get("jurisdiction") or UNKNOWN_LEGAL_CONTEXT)
        prior_blank = prior == UNKNOWN_LEGAL_CONTEXT
        selected_before = _context_has_selected_state(current, dependent_proof)
        if resolved != prior and (not prior_blank or selected_before):
            changed.append("jurisdiction")
        current["jurisdiction"] = resolved
        current["jurisdiction_explicit"] = resolved != UNKNOWN_LEGAL_CONTEXT

    for role in LEGAL_DATE_ROLES:
        if role not in proposed:
            continue
        classified = classify_legal_date(proposed.get(role), role=role)
        prior_raw = _date_raw(current.get(role))
        new_raw = _date_raw(classified)
        if prior_raw and new_raw != prior_raw:
            changed.append(role)
        elif not prior_raw and new_raw and _context_has_selected_state(current, dependent_proof):
            changed.append(role)
        current[role] = classified

    if "event_dates" in proposed:
        event_dates = []
        for item in proposed.get("event_dates") or []:
            event_dates.append(classify_legal_date(item, role=DATE_ROLE_EVENT))
        prior_event_raws = [_date_raw(item) for item in (current.get("event_dates") or []) if _date_raw(item)]
        new_event_raws = [_date_raw(item) for item in event_dates if _date_raw(item)]
        if prior_event_raws and prior_event_raws != new_event_raws:
            changed.append("event_dates")
        current["event_dates"] = event_dates
        if len(event_dates) == 1:
            current["event_date"] = event_dates[0]

    if changed:
        current["context_revision"] = int(current.get("context_revision") or 0) + 1
        current["changed_fields"] = changed
        prior_applicability = str(current.get("selected_rule_applicability") or UNKNOWN_LEGAL_CONTEXT)
        if prior_applicability not in {"", UNKNOWN_LEGAL_CONTEXT}:
            current["selected_rule_applicability"] = "invalidated"
            current["invalidated_rule_applicability"] = prior_applicability
        else:
            current["selected_rule_applicability"] = UNKNOWN_LEGAL_CONTEXT
        proof_items = list(dependent_proof if dependent_proof is not None else current.get("dependent_proof") or [])
        invalidated_proof: List[Dict[str, Any]] = []
        for item in proof_items:
            if not isinstance(item, dict):
                continue
            proof_state = str(item.get("proof_state") or item.get("status") or UNKNOWN_LEGAL_CONTEXT).strip().lower()
            updated_item = dict(item)
            if proof_state not in {"", UNKNOWN_LEGAL_CONTEXT}:
                updated_item["proof_state"] = "invalidated"
                updated_item["invalidated_by"] = "legal_context_change"
                updated_item["invalidated_from_proof_state"] = proof_state
            invalidated_proof.append(updated_item)
        current["dependent_proof"] = invalidated_proof
        prior_proof = str(current.get("proof_state") or UNKNOWN_LEGAL_CONTEXT).strip().lower()
        if prior_proof not in {"", UNKNOWN_LEGAL_CONTEXT}:
            current["proof_state"] = "invalidated"
        else:
            current["proof_state"] = UNKNOWN_LEGAL_CONTEXT
    else:
        current["changed_fields"] = []
        if dependent_proof is not None:
            current["dependent_proof"] = [dict(item) for item in dependent_proof if isinstance(item, dict)]

    jurisdiction = str(current.get("jurisdiction") or UNKNOWN_LEGAL_CONTEXT)
    current["status"] = UNKNOWN_LEGAL_CONTEXT if jurisdiction == UNKNOWN_LEGAL_CONTEXT else "explicit"
    current["questions"] = questions_for_legal_context(current)
    return current


def _context_has_selected_state(context: Dict[str, Any], dependent_proof: Optional[List[Dict[str, Any]]]) -> bool:
    applicability = str(context.get("selected_rule_applicability") or UNKNOWN_LEGAL_CONTEXT).strip().lower()
    proof_state = str(context.get("proof_state") or UNKNOWN_LEGAL_CONTEXT).strip().lower()
    if applicability not in {"", UNKNOWN_LEGAL_CONTEXT} or proof_state not in {"", UNKNOWN_LEGAL_CONTEXT}:
        return True
    for item in dependent_proof or context.get("dependent_proof") or []:
        if not isinstance(item, dict):
            continue
        state = str(item.get("proof_state") or item.get("status") or UNKNOWN_LEGAL_CONTEXT).strip().lower()
        if state not in {"", UNKNOWN_LEGAL_CONTEXT}:
            return True
    return False


def questions_for_legal_context(
    context: Optional[Dict[str, Any]],
    *,
    selecting_rules: bool = False,
) -> List[Dict[str, Any]]:
    """Questions to ask the user. Missing context is not filled in for them."""
    legal_context = context if isinstance(context, dict) else empty_legal_context()
    questions: List[Dict[str, Any]] = []
    jurisdiction = str(legal_context.get("jurisdiction") or UNKNOWN_LEGAL_CONTEXT)
    if jurisdiction == UNKNOWN_LEGAL_CONTEXT:
        questions.append({
            "question_id": "legal_context.jurisdiction",
            "field": "jurisdiction",
            "prompt": (
                "Which jurisdiction's law applies? Name the state or say federal. "
                "Unresolved jurisdiction stays unknown; Oregon and federal court are not assumed."
            ),
            "reason": "unresolved_jurisdiction",
        })
    event_dates = [
        item for item in (legal_context.get("event_dates") or [])
        if isinstance(item, dict) and _date_raw(item)
    ]
    event_date = legal_context.get("event_date") if isinstance(legal_context.get("event_date"), dict) else {}
    if not event_dates and not _date_raw(event_date):
        questions.append({
            "question_id": "legal_context.event_dates",
            "field": "event_date",
            "prompt": (
                "What dates or date ranges are relevant to the events? "
                "If you know only a range, give the range. A single day will not be invented."
            ),
            "reason": "missing_event_dates",
        })
    if selecting_rules and not _date_raw(legal_context.get("applicable_law_date")):
        questions.append({
            "question_id": "legal_context.applicable_law_date",
            "field": "applicable_law_date",
            "prompt": "What date should be used to decide which version of the law applies?",
            "reason": "missing_applicable_law_date",
        })
    if selecting_rules and not _date_raw(legal_context.get("filing_reference_date")):
        questions.append({
            "question_id": "legal_context.filing_reference_date",
            "field": "filing_reference_date",
            "prompt": "What filing or reference date should be kept separate from the event date?",
            "reason": "missing_filing_reference_date",
        })
    return questions


def select_requirement_applicability(
    requirement: Optional[Dict[str, Any]],
    legal_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Select a requirement only against explicit jurisdiction and date roles.

    Implicit Oregon or federal selection is refused. Missing context stays unknown.
    """
    requirement_record = requirement if isinstance(requirement, dict) else {}
    context = legal_context if isinstance(legal_context, dict) else empty_legal_context()
    jurisdiction = resolve_explicit_jurisdiction(context.get("jurisdiction"))
    requirement_jurisdiction = resolve_explicit_jurisdiction(
        requirement_record.get("jurisdiction") or requirement_record.get("state")
    )
    applicable_law_date = context.get("applicable_law_date") if isinstance(context.get("applicable_law_date"), dict) else {}
    if jurisdiction == UNKNOWN_LEGAL_CONTEXT or requirement_jurisdiction == UNKNOWN_LEGAL_CONTEXT:
        return {
            "applicability": UNKNOWN_LEGAL_CONTEXT,
            "selected": False,
            "reason": "unresolved_legal_context",
            "jurisdiction": UNKNOWN_LEGAL_CONTEXT if jurisdiction == UNKNOWN_LEGAL_CONTEXT else jurisdiction,
            "requirement_jurisdiction": requirement_jurisdiction,
            "context_revision": int(context.get("context_revision") or 0),
        }
    if jurisdiction != requirement_jurisdiction:
        return {
            "applicability": UNKNOWN_LEGAL_CONTEXT,
            "selected": False,
            "reason": "jurisdiction_not_selected",
            "jurisdiction": jurisdiction,
            "requirement_jurisdiction": requirement_jurisdiction,
            "context_revision": int(context.get("context_revision") or 0),
        }
    if not _date_raw(applicable_law_date):
        return {
            "applicability": UNKNOWN_LEGAL_CONTEXT,
            "selected": False,
            "reason": "missing_applicable_law_date",
            "jurisdiction": jurisdiction,
            "requirement_jurisdiction": requirement_jurisdiction,
            "context_revision": int(context.get("context_revision") or 0),
        }
    stored_revision = requirement_record.get("context_revision")
    current_revision = int(context.get("context_revision") or 0)
    if stored_revision is not None and int(stored_revision) != current_revision:
        return {
            "applicability": "invalidated",
            "selected": False,
            "reason": "stale_legal_context",
            "jurisdiction": jurisdiction,
            "requirement_jurisdiction": requirement_jurisdiction,
            "context_revision": current_revision,
        }
    return {
        "applicability": "selected",
        "selected": True,
        "reason": "explicit_context",
        "jurisdiction": jurisdiction,
        "requirement_jurisdiction": requirement_jurisdiction,
        "applicable_law_date": applicable_law_date,
        "event_date": context.get("event_date"),
        "filing_reference_date": context.get("filing_reference_date"),
        "corpus_retrieval_date": context.get("corpus_retrieval_date"),
        "context_revision": current_revision,
    }


def legal_requirement_search_plan(
    program: Optional[Dict[str, Any]],
    *,
    state: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide authority searches without implying Oregon or federal law."""
    program_record = program if isinstance(program, dict) else {}
    families = {
        str(family or "").strip()
        for family in (program_record.get("authority_families") or [])
        if str(family or "").strip()
    }
    jurisdiction = resolve_explicit_jurisdiction(state or program_record.get("jurisdiction"))
    state_code = jurisdiction if jurisdiction not in {UNKNOWN_LEGAL_CONTEXT, "federal"} else ""
    search_federal = jurisdiction == "federal"
    search_state = bool(state_code)
    include_all = not families
    return {
        "jurisdiction": jurisdiction,
        "state_code": state_code,
        "context_status": UNKNOWN_LEGAL_CONTEXT if jurisdiction == UNKNOWN_LEGAL_CONTEXT else "explicit",
        "selected_rule_applicability": UNKNOWN_LEGAL_CONTEXT if jurisdiction == UNKNOWN_LEGAL_CONTEXT else "unselected",
        "search_us_code": search_federal and (include_all or "statute" in families),
        "search_federal_register": search_federal and (include_all or "regulation" in families),
        "search_state_laws": search_state and (include_all or "statute" in families),
        "search_state_administrative_rules": search_state and (include_all or "administrative_rule" in families),
        "search_case_law": search_federal and (include_all or "case_law" in families or "docket_material" in families),
        "authority_families": sorted(families),
    }

LEGAL_SOURCE_AVAILABILITY = {
    "federal_statutes": _search_us_code_async is not None,
    "federal_regulations": _search_federal_register_async is not None,
    "case_law": _search_recap_documents_async is not None,
    "state_statutes": (
        _search_state_law_corpus_async is not None
        or _scrape_state_laws_async is not None
        or _stream_ipfs_state_laws_async is not None
    ),
    "administrative_rules": _search_state_law_corpus_async is not None or _scrape_state_admin_rules_async is not None,
    "state_laws_ipfs_stream": _stream_ipfs_state_laws_async is not None,
}

LEGAL_SCRAPERS_AVAILABLE = any(LEGAL_SOURCE_AVAILABILITY.values())
LEGAL_SCRAPERS_ERROR = (
    _us_code_error
    or _federal_register_error
    or _recap_error
    or _federal_register_hf_error
    or _state_law_corpus_error
    or _state_laws_scrape_error
    or _state_admin_rules_scrape_error
    or _state_code_map_error
)

# Environment variable that enables the IPFS streaming live-lookup pass.
# Set to "1", "true", "yes", or "on" to allow search_state_laws to attempt
# IPFS streaming when the HuggingFace corpus / parquet backends return no
# results and the ipfs_datasets_py state_laws_ipfs_stream adapter is importable.
_IPFS_STREAM_STATE_LAWS_ENV = "COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM"


def _search_ipfs_state_laws_stream(
    query: str,
    *,
    state_code: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """Attempt a live IPFS-streaming search of the state-laws dataset.

    Uses the ``ipfs_datasets_py.datasets.state_laws_ipfs_stream`` adapter when
    available.  Returns an empty list if the adapter is absent, the IPFS
    backend is unavailable, or any error occurs.  Guarded by
    ``COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM=1``.
    """
    import os

    if os.environ.get(_IPFS_STREAM_STATE_LAWS_ENV, "").strip() not in {"1", "true", "yes", "on"}:
        return []
    if _stream_ipfs_state_laws_async is None:
        return []
    try:
        payload = run_async_compat(
            _stream_ipfs_state_laws_async(
                {
                    "query": query,
                    "state": state_code,
                    "top_k": max_results,
                    "output_format": "json",
                }
            )
        )
        return _normalize_payload_results(
            payload,
            "statute",
            "state_law_ipfs_stream",
            query=query,
            operation="search_state_laws_ipfs_stream",
            max_results=max_results,
        )
    except Exception:
        return []


def _extract_payload_items(payload: Dict[str, Any], *keys: str) -> List[Dict[str, Any]]:
    for key in keys:
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _merge_nested_case_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(item)
    case_payload = item.get("case")
    if isinstance(case_payload, dict):
        if not merged.get("title"):
            merged["title"] = case_payload.get("title") or case_payload.get("name") or case_payload.get("case_name")
        if not merged.get("case_name"):
            merged["case_name"] = case_payload.get("case_name") or case_payload.get("name")
        if not merged.get("citation"):
            merged["citation"] = case_payload.get("citation") or case_payload.get("identifier")
        if not merged.get("url"):
            merged["url"] = case_payload.get("url") or case_payload.get("absolute_url")
        if not merged.get("content"):
            merged["content"] = case_payload.get("content") or case_payload.get("snippet") or case_payload.get("summary")
    return merged


def _normalize_authority(
    item: Dict[str, Any],
    authority_type: str,
    source: str,
    *,
    query: str,
    operation: str,
    upstream_collection: str,
) -> Dict[str, Any]:
    item = _merge_nested_case_fields(item)
    url = item.get("url") or item.get("absolute_url") or item.get("html_url") or item.get("pdf_url") or ""
    citation = (
        item.get("citation")
        or item.get("document_number")
        or item.get("identifier")
        or item.get("id")
        or item.get("title")
        or item.get("name")
        or ""
    )
    title = item.get("title") or item.get("name") or item.get("case_name") or citation
    content = (
        item.get("content")
        or item.get("text")
        or item.get("snippet")
        or item.get("summary")
        or ""
    )
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    normalized = dict(item)
    normalized.update(
        {
            "type": item.get("type", authority_type),
            "source": item.get("source", source),
            "citation": citation,
            "title": title,
            "content": content,
            "url": url,
            "metadata": metadata,
            "relevance_score": item.get("relevance_score", 0.5),
        }
    )
    return with_adapter_metadata(
        normalized,
        operation=operation,
        backend_available=True,
        implementation_status="normalized",
        extra_metadata={
            "authority_type": normalized["type"],
            "query": query,
            "source": normalized["source"],
            "upstream_collection": upstream_collection,
        },
    )


def _attach_hf_corpus_metadata(
    records: List[Dict[str, Any]],
    *,
    hf_dataset_id: str,
    retrieval_backend: str,
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        metadata = dict(payload.get("metadata") or {})
        details = dict(metadata.get("details") or {})
        details.setdefault("hf_dataset_id", hf_dataset_id)
        details.setdefault("retrieval_backend", retrieval_backend)
        metadata["details"] = details
        payload["metadata"] = metadata
        enriched.append(payload)
    return enriched


def _normalize_scraped_authority(
    item: Dict[str, Any],
    authority_type: str,
    source: str,
    *,
    query: str,
    operation: str,
) -> Dict[str, Any]:
    normalized_item = dict(item)
    citation = (
        normalized_item.get("citation")
        or normalized_item.get("section_number")
        or normalized_item.get("rule_number")
        or normalized_item.get("identifier")
        or normalized_item.get("id")
        or normalized_item.get("title")
        or ""
    )
    normalized_item.setdefault(
        "title",
        normalized_item.get("section_name")
        or normalized_item.get("rule_title")
        or normalized_item.get("heading")
        or citation,
    )
    normalized_item.setdefault(
        "content",
        normalized_item.get("full_text")
        or normalized_item.get("text")
        or normalized_item.get("summary")
        or normalized_item.get("snippet")
        or "",
    )
    normalized_item.setdefault(
        "url",
        normalized_item.get("source_url")
        or normalized_item.get("url")
        or "",
    )
    normalized_item.setdefault("citation", citation)
    normalized_item.setdefault("relevance_score", normalized_item.get("score", 0.4))
    return _normalize_authority(
        normalized_item,
        authority_type,
        source,
        query=query,
        operation=operation,
        upstream_collection="data",
    )


def _normalize_payload_results(
    payload: Dict[str, Any],
    authority_type: str,
    source: str,
    *,
    query: str,
    operation: str,
    upstream_collection: str = "results",
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    items = _extract_payload_items(payload, upstream_collection, "results", "documents", "hits")
    return [
        _normalize_authority(
            item,
            authority_type,
            source,
            query=query,
            operation=operation,
            upstream_collection=upstream_collection,
        )
        for item in items[:max_results]
    ]


def _search_scraped_records(
    query: str,
    *,
    authority_type: str,
    source: str,
    operation: str,
    payload: Dict[str, Any],
    max_results: int,
) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []

    items = payload.get("data")
    if not isinstance(items, list):
        return []

    lowered_query = str(query or "").strip().lower()
    query_terms = [term for term in lowered_query.split() if len(term) > 2]
    scored: List[tuple[int, Dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(
            str(item.get(field) or "")
            for field in (
                "full_text",
                "text",
                "content",
                "summary",
                "snippet",
                "section_name",
                "title",
                "heading",
                "rule_title",
                "agency",
                "section_number",
                "rule_number",
            )
        ).lower()
        score = 0
        if lowered_query and lowered_query in haystack:
            score += 3
        score += sum(1 for term in query_terms if term in haystack)
        if score <= 0 and lowered_query:
            continue
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        _normalize_scraped_authority(
            item,
            authority_type,
            source,
            query=query,
            operation=operation,
        )
        for _, item in scored[:max_results]
    ]


def _search_hf_parquet_text(
    *,
    query: str,
    hf_dataset_id: str,
    preferred_files: List[str],
    authority_type: str,
    source: str,
    operation: str,
    max_results: int,
    state_code: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    query_text = str(query or "").strip()
    if not query_text or not preferred_files:
        return []

    try:
        from huggingface_hub import hf_hub_download
        import duckdb
        import pyarrow.parquet as pq
    except Exception:
        return []

    local_file = None
    for candidate in preferred_files:
        try:
            local_file = hf_hub_download(
                repo_id=hf_dataset_id,
                repo_type="dataset",
                filename=candidate,
            )
            if diagnostics is not None:
                diagnostics.setdefault("parquet", {}).setdefault("attempted_files", []).append(
                    {"filename": candidate, "available": True}
                )
            if local_file:
                break
        except Exception:
            if diagnostics is not None:
                diagnostics.setdefault("parquet", {}).setdefault("attempted_files", []).append(
                    {"filename": candidate, "available": False}
                )
            continue

    if not local_file:
        _set_hf_search_warning(
            diagnostics,
            warning_code="hf_dataset_files_missing",
            warning_message=(
                f"Hugging Face dataset {hf_dataset_id} does not currently publish any of the expected parquet files"
                + (f" for state {state_code}." if state_code else ".")
            ),
        )
        return []

    try:
        schema_names = list(pq.ParquetFile(local_file).schema_arrow.names)
    except Exception:
        return []

    text_candidates = [
        "full_text",
        "text",
        "content",
        "summary",
        "snippet",
        "section_name",
        "title",
        "heading",
        "rule_title",
        "agency",
        "section_number",
        "rule_number",
    ]
    selected_text_fields = [field for field in text_candidates if field in schema_names]
    if not selected_text_fields:
        return []

    state_field = next(
        (field for field in ("state_code", "state", "state_abbr") if field in schema_names),
        None,
    )
    if diagnostics is not None:
        diagnostics.setdefault("parquet", {})["selected_file"] = local_file.rsplit("/", 1)[-1]
        diagnostics["parquet"]["state_field"] = state_field or ""
    row_limit = max(max_results * 8, 25)

    haystack_expr = " || ' ' || ".join(
        [f"coalesce(cast({field} as varchar), '')" for field in selected_text_fields]
    )
    lowered_query = query_text.lower()
    query_terms = [term for term in lowered_query.split() if len(term) > 2]
    if not query_terms:
        query_terms = [lowered_query]

    score_parts = ["CASE WHEN lower(" + haystack_expr + ") LIKE ? THEN 5 ELSE 0 END"]
    score_params: List[str] = [f"%{lowered_query}%"]
    term_checks: List[str] = []
    term_params: List[str] = []
    for term in query_terms:
        score_parts.append("CASE WHEN lower(" + haystack_expr + ") LIKE ? THEN 1 ELSE 0 END")
        score_params.append(f"%{term}%")
        term_checks.append("lower(" + haystack_expr + ") LIKE ?")
        term_params.append(f"%{term}%")

    where_clauses = ["(" + " OR ".join(term_checks) + ")"] if term_checks else []
    where_params: List[str] = list(term_params)
    if state_code and state_field:
        where_clauses.append(f"upper(coalesce(cast({state_field} as varchar), '')) = ?")
        where_params.append(str(state_code).upper())

    query_sql = f"""
        SELECT *, ({' + '.join(score_parts)}) AS __score
        FROM parquet_scan(?)
        WHERE {' AND '.join(where_clauses) if where_clauses else 'TRUE'}
        ORDER BY __score DESC
        LIMIT {int(row_limit)}
    """
    params: List[Any] = list(score_params)
    params.append(local_file)
    params.extend(where_params)

    try:
        con = duckdb.connect()
        if state_code and state_field:
            state_row_count = con.execute(
                f"select count(*) from parquet_scan(?) where upper(coalesce(cast({state_field} as varchar), '')) = ?",
                [local_file, str(state_code).upper()],
            ).fetchone()[0]
            if diagnostics is not None:
                diagnostics.setdefault("parquet", {})["state_row_count"] = int(state_row_count)
            if int(state_row_count or 0) == 0:
                _set_hf_search_warning(
                    diagnostics,
                    warning_code="hf_state_rows_missing",
                    warning_message=(
                        f"Hugging Face dataset {hf_dataset_id} does not currently expose rows for requested state {state_code}."
                    ),
                )
        rows = con.execute(query_sql, params).fetchall()
        columns = [desc[0] for desc in con.description]
        con.close()
    except Exception:
        return []

    normalized_items: List[Dict[str, Any]] = []
    for row in rows[:max_results]:
        item = dict(zip(columns, row))
        item.pop("__score", None)
        normalized_items.append(
            _normalize_scraped_authority(
                item,
                authority_type,
                source,
                query=query,
                operation=operation,
            )
        )

    return _attach_hf_corpus_metadata(
        normalized_items,
        hf_dataset_id=hf_dataset_id,
        retrieval_backend="huggingface_parquet",
    )


def search_us_code(query: str, title: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    if _search_us_code_async is None:
        return []
    payload = run_async_compat(
        _search_us_code_async(
            query=query,
            titles=[title] if title else None,
            max_results=max_results,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    items = _extract_payload_items(payload, "results", "documents")
    return [
        _normalize_authority(
            item,
            "statute",
            "us_code",
            query=query,
            operation="search_us_code",
            upstream_collection="results",
        )
        for item in items[:max_results]
    ]


def search_federal_register(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    search_key = "search_federal_register"
    diagnostics: Dict[str, Any] = {
        "search_key": search_key,
        "query": str(query or ""),
        "hf_dataset_id": DEFAULT_FEDERAL_REGISTER_DATASET_ID,
        "attempted_backends": [],
        "warning_code": "",
        "warning_message": "",
    }
    _set_last_legal_search_diagnostic(search_key, None)

    if _search_federal_register_hf_index_async is not None:
        diagnostics["attempted_backends"].append("huggingface_index")
        try:
            payload = run_async_compat(
                _search_federal_register_hf_index_async(
                    {
                        "query_text": query,
                        "top_k": max_results,
                        "auto_setup_venv": False,
                    }
                )
            )
            hf_results = _normalize_payload_results(
                payload,
                "regulation",
                "federal_register",
                query=query,
                operation="search_federal_register_hf_index",
                upstream_collection="hits",
                max_results=max_results,
            )
            if hf_results:
                diagnostics["selected_backend"] = "huggingface_index"
                diagnostics["final_status"] = "success"
                _set_last_legal_search_diagnostic(search_key, diagnostics)
                return _attach_hf_corpus_metadata(
                    hf_results,
                    hf_dataset_id=DEFAULT_FEDERAL_REGISTER_DATASET_ID,
                    retrieval_backend="huggingface_index",
                )
            diagnostics["hf_index_status"] = "empty"
        except Exception as exc:
            # The upstream API below is an intentional availability fallback,
            # but an index runtime failure must not be indistinguishable from
            # an index that returned no matching records.
            diagnostics["hf_index_failure"] = {
                "backend": "huggingface_index",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "fallback": "upstream_api",
            }
            _set_hf_search_warning(
                diagnostics,
                warning_code="hf_index_search_failed",
                warning_message=(
                    "Federal Register Hugging Face index search failed; "
                    "falling back to the upstream API."
                ),
            )
            logger.warning(
                "Federal Register Hugging Face index search failed; "
                "falling back to the upstream API",
                exc_info=True,
            )

    if _search_federal_register_async is None:
        diagnostics["selected_backend"] = ""
        diagnostics["final_status"] = "empty_upstream_api_unavailable"
        _set_last_legal_search_diagnostic(search_key, diagnostics)
        return []
    diagnostics["attempted_backends"].append("upstream_api")
    payload = run_async_compat(
        _search_federal_register_async(
            keywords=query,
            start_date=start_date,
            end_date=end_date,
            limit=max_results,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        diagnostics["selected_backend"] = ""
        diagnostics["final_status"] = "empty_upstream_api_failure"
        _set_last_legal_search_diagnostic(search_key, diagnostics)
        return []
    items = _extract_payload_items(payload, "documents", "results")
    results = [
        _normalize_authority(
            item,
            "regulation",
            "federal_register",
            query=query,
            operation="search_federal_register",
            upstream_collection="documents",
        )
        for item in items[:max_results]
    ]
    diagnostics["selected_backend"] = "upstream_api"
    diagnostics["final_status"] = "success" if results else "empty"
    _set_last_legal_search_diagnostic(search_key, diagnostics)
    return _attach_hf_corpus_metadata(
        results,
        hf_dataset_id=DEFAULT_FEDERAL_REGISTER_DATASET_ID,
        retrieval_backend="upstream_api",
    )


def search_recap_documents(
    query: str,
    court: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    if _search_recap_documents_async is None:
        return []
    payload = run_async_compat(
        _search_recap_documents_async(
            query=query,
            court=court,
            limit=max_results,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    items = _extract_payload_items(payload, "documents", "results")
    return [
        _normalize_authority(
            item,
            "case_law",
            "recap",
            query=query,
            operation="search_recap_documents",
            upstream_collection="documents",
        )
        for item in items[:max_results]
    ]


def search_state_laws(
    query: str,
    state: Optional[str] = None,
    max_results: int = 10,
    collection_name: Optional[str] = None,
    embedding_model: str = DEFAULT_LEGAL_QUERY_EMBEDDING_MODEL,
    embedding_provider: Optional[str] = None,
    allow_live_scrape_fallback: bool = True,
) -> List[Dict[str, Any]]:
    state_code = _resolve_state_code(state)
    if not state_code:
        _set_last_legal_search_diagnostic(
            "search_state_laws",
            {
                "search_key": "search_state_laws",
                "final_status": "unknown_jurisdiction",
                "state_code": "",
                "context_status": UNKNOWN_LEGAL_CONTEXT,
            },
        )
        return []
    diagnostics = _build_hf_search_diagnostic(
        search_key="search_state_laws",
        query=query,
        state_code=state_code,
        hf_dataset_id=DEFAULT_STATE_LAWS_DATASET_ID,
        preferred_files=[f"STATE-{state_code}.parquet", "state_laws_all_states.parquet"],
    )
    _set_last_legal_search_diagnostic("search_state_laws", None)
    if _search_state_law_corpus_async is not None:
        diagnostics["attempted_backends"].append("huggingface_corpus")
        query_vector = _build_query_vector(
            query,
            model_name=embedding_model,
            provider=embedding_provider,
            diagnostics=diagnostics,
        )
        if query_vector is not None:
            payload = run_async_compat(
                _search_state_law_corpus_async(
                    {
                        "collection_name": collection_name or f"{state_code.lower()}_docs",
                        "query_text": query,
                        "query_vector": query_vector,
                        "state": state_code,
                        "top_k": max_results,
                        "enrich_with_cases": True,
                        "auto_setup_venv": False,
                    }
                )
            )
            results = _normalize_payload_results(
                payload,
                "statute",
                "state_law",
                query=query,
                operation="search_state_laws",
                max_results=max_results,
            )
            if results:
                diagnostics["selected_backend"] = "huggingface_corpus"
                _set_last_legal_search_diagnostic("search_state_laws", diagnostics)
                return _attach_hf_corpus_metadata(
                    results,
                    hf_dataset_id=DEFAULT_STATE_LAWS_DATASET_ID,
                    retrieval_backend="huggingface_corpus",
                )
        else:
            diagnostics["corpus_status"] = "query_vector_unavailable"

    diagnostics["attempted_backends"].append("huggingface_parquet")
    parquet_results = _search_hf_parquet_text(
        query=query,
        hf_dataset_id=DEFAULT_STATE_LAWS_DATASET_ID,
        preferred_files=[f"STATE-{state_code}.parquet", "state_laws_all_states.parquet"],
        authority_type="statute",
        source="state_law",
        operation="search_state_laws_hf_parquet",
        max_results=max_results,
        state_code=state_code,
        diagnostics=diagnostics,
    )
    if parquet_results:
        diagnostics["selected_backend"] = "huggingface_parquet"
        _set_last_legal_search_diagnostic("search_state_laws", diagnostics)
        return parquet_results

    # Try live IPFS streaming before falling back to full live scrape.
    # Gated by COMPLAINT_ENABLE_IPFS_STATE_LAWS_STREAM=1.
    diagnostics["attempted_backends"].append("ipfs_stream")
    ipfs_stream_results = _search_ipfs_state_laws_stream(
        query,
        state_code=state_code,
        max_results=max_results,
    )
    if ipfs_stream_results:
        diagnostics["selected_backend"] = "ipfs_stream"
        _set_last_legal_search_diagnostic("search_state_laws", diagnostics)
        return _attach_hf_corpus_metadata(
            ipfs_stream_results,
            hf_dataset_id=DEFAULT_STATE_LAWS_DATASET_ID,
            retrieval_backend="ipfs_stream",
        )

    if not allow_live_scrape_fallback:
        diagnostics["selected_backend"] = ""
        diagnostics["final_status"] = "empty_without_live_fallback"
        _set_last_legal_search_diagnostic("search_state_laws", diagnostics)
        return []
    if _scrape_state_laws_async is None:
        diagnostics["selected_backend"] = ""
        diagnostics["final_status"] = "empty_live_scrape_unavailable"
        _set_last_legal_search_diagnostic("search_state_laws", diagnostics)
        return []

    diagnostics["attempted_backends"].append("live_scrape_fallback")
    payload = run_async_compat(
        _scrape_state_laws_async(
            {
                "states": [state_code],
                "output_format": "json",
                "include_metadata": True,
                "max_statutes": max(max_results * 4, max_results),
                "hydrate_statute_text": True,
                "parallel_workers": 2,
                "per_state_retry_attempts": 0,
                "retry_zero_statute_states": False,
            }
        )
    )
    return _attach_hf_corpus_metadata(
        _search_scraped_records(
            query,
            authority_type="statute",
            source="state_law",
            operation="search_state_laws_live_scrape",
            payload=payload,
            max_results=max_results,
        ),
        hf_dataset_id=DEFAULT_STATE_LAWS_DATASET_ID,
        retrieval_backend="live_scrape_fallback",
    )
    diagnostics["selected_backend"] = "live_scrape_fallback" if payload else ""
    diagnostics["final_status"] = "live_scrape_fallback"
    _set_last_legal_search_diagnostic("search_state_laws", diagnostics)
    return payload


def search_state_administrative_rules(
    query: str,
    state: Optional[str] = None,
    max_results: int = 10,
    collection_name: Optional[str] = None,
    embedding_model: str = DEFAULT_LEGAL_QUERY_EMBEDDING_MODEL,
    embedding_provider: Optional[str] = None,
    allow_live_scrape_fallback: bool = True,
) -> List[Dict[str, Any]]:
    state_code = _resolve_state_code(state)
    if not state_code:
        _set_last_legal_search_diagnostic(
            "search_state_administrative_rules",
            {
                "search_key": "search_state_administrative_rules",
                "final_status": "unknown_jurisdiction",
                "state_code": "",
                "context_status": UNKNOWN_LEGAL_CONTEXT,
            },
        )
        return []
    diagnostics = _build_hf_search_diagnostic(
        search_key="search_state_administrative_rules",
        query=query,
        state_code=state_code,
        hf_dataset_id=DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
        preferred_files=[f"STATE-{state_code}.parquet", "state_admin_rules_all_states.parquet"],
    )
    _set_last_legal_search_diagnostic("search_state_administrative_rules", None)
    if _search_state_law_corpus_async is not None:
        diagnostics["attempted_backends"].append("huggingface_corpus")
        query_vector = _build_query_vector(
            query,
            model_name=embedding_model,
            provider=embedding_provider,
            diagnostics=diagnostics,
        )
        if query_vector is not None:
            payload = run_async_compat(
                _search_state_law_corpus_async(
                    {
                        "collection_name": collection_name or f"{state_code.lower()}_admin_rules",
                        "query_text": query,
                        "query_vector": query_vector,
                        "state": state_code,
                        "hf_dataset_id": DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
                        "hf_dataset_ids": [DEFAULT_STATE_ADMIN_RULES_DATASET_ID],
                        "top_k": max_results,
                        "enrich_with_cases": True,
                        "auto_setup_venv": False,
                    }
                )
            )
            results = _normalize_payload_results(
                payload,
                "administrative_rule",
                "state_admin_rules",
                query=query,
                operation="search_state_administrative_rules",
                max_results=max_results,
            )
            if results:
                diagnostics["selected_backend"] = "huggingface_corpus"
                _set_last_legal_search_diagnostic("search_state_administrative_rules", diagnostics)
                return _attach_hf_corpus_metadata(
                    results,
                    hf_dataset_id=DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
                    retrieval_backend="huggingface_corpus",
                )
        else:
            diagnostics["corpus_status"] = "query_vector_unavailable"

    diagnostics["attempted_backends"].append("huggingface_parquet")
    parquet_results = _search_hf_parquet_text(
        query=query,
        hf_dataset_id=DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
        preferred_files=[f"STATE-{state_code}.parquet", "state_admin_rules_all_states.parquet"],
        authority_type="administrative_rule",
        source="state_admin_rules",
        operation="search_state_administrative_rules_hf_parquet",
        max_results=max_results,
        state_code=state_code,
        diagnostics=diagnostics,
    )
    if parquet_results:
        diagnostics["selected_backend"] = "huggingface_parquet"
        _set_last_legal_search_diagnostic("search_state_administrative_rules", diagnostics)
        return parquet_results

    if not allow_live_scrape_fallback:
        diagnostics["selected_backend"] = ""
        diagnostics["final_status"] = "empty_without_live_fallback"
        _set_last_legal_search_diagnostic("search_state_administrative_rules", diagnostics)
        return []
    if _scrape_state_admin_rules_async is None:
        diagnostics["selected_backend"] = ""
        diagnostics["final_status"] = "empty_live_scrape_unavailable"
        _set_last_legal_search_diagnostic("search_state_administrative_rules", diagnostics)
        return []

    diagnostics["attempted_backends"].append("live_scrape_fallback")
    payload = run_async_compat(
        _scrape_state_admin_rules_async(
            {
                "states": [state_code],
                "output_format": "json",
                "include_metadata": True,
                "max_rules": max(max_results * 4, max_results),
                "hydrate_rule_text": True,
                "parallel_workers": 2,
                "per_state_retry_attempts": 0,
                "retry_zero_rule_states": False,
            }
        )
    )
    return _attach_hf_corpus_metadata(
        _search_scraped_records(
            query,
            authority_type="administrative_rule",
            source="state_admin_rules",
            operation="search_state_administrative_rules_live_scrape",
            payload=payload,
            max_results=max_results,
        ),
        hf_dataset_id=DEFAULT_STATE_ADMIN_RULES_DATASET_ID,
        retrieval_backend="live_scrape_fallback",
    )
    diagnostics["selected_backend"] = "live_scrape_fallback" if payload else ""
    diagnostics["final_status"] = "live_scrape_fallback"
    _set_last_legal_search_diagnostic("search_state_administrative_rules", diagnostics)
    return payload


# ---------------------------------------------------------------------------
# Legal corpus containment — constrain FOL assertions to grounded citations
# ---------------------------------------------------------------------------

# Environment variable that points to a local vector index directory built from
# the legal corpus.  When set, constrain_assertions_to_corpus will try a
# semantic (embedding-based) similarity search as a fourth grounding pass.
_LEGAL_VECTOR_INDEX_DIR_ENV = "COMPLAINT_LEGAL_VECTOR_INDEX_DIR"


def _search_legal_vector_index(
    query: str,
    *,
    index_dir: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """Try a semantic vector search against a pre-built legal corpus index.

    Returns a list of normalised authority dicts (same shape as other
    ``search_*`` helpers) or an empty list when the index is absent / not
    set up.
    """
    from .vector_store import search_vector_index

    result = search_vector_index(
        query,
        index_name="legal_corpus",
        index_dir=index_dir,
        top_k=max_results,
    )
    if not isinstance(result, dict) or result.get("status") not in {"success", "available"}:
        return []
    raw_hits: List[Dict[str, Any]] = list(result.get("results") or [])
    normalised: List[Dict[str, Any]] = []
    for item in raw_hits[:max_results]:
        if not isinstance(item, dict):
            continue
        normalised.append(
            _normalize_authority(
                item,
                str(item.get("type") or "legal_corpus"),
                str(item.get("source") or "vector_index"),
                query=query,
                operation="search_legal_vector_index",
                upstream_collection="results",
            )
        )
    return normalised


def constrain_assertions_to_corpus(
    assertions: List[Dict[str, Any]],
    *,
    state: Optional[str] = None,
    max_results_per_assertion: int = 3,
    allow_live_scrape_fallback: bool = False,
    legal_vector_index_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Ground *assertions* against the legal corpus and classify each one.

    For every assertion dict (expected to have at least a ``text`` key) the
    function issues a search against the combined federal and state-law corpus
    (US Code + Federal Register + state laws) and marks each assertion as one
    of:

    * ``grounded``  — at least one authoritative corpus document was found.
    * ``ungrounded`` — no corpus document could be located.

    The summary dict exposes ``grounded_count``, ``ungrounded_count``, and
    ``corpus_coverage_percent`` for downstream use by the proof pipeline and
    the editor guardrails.

    Parameters
    ----------
    assertions:
        List of assertion dicts.  Each should carry at minimum a ``text`` key
        with the assertion text to search.  A ``assertion_id`` key is used for
        tracking; one is synthesised if absent.
    state:
        Optional two-letter state code to narrow state-law searches.
    max_results_per_assertion:
        How many corpus hits to return per assertion.
    allow_live_scrape_fallback:
        Whether to permit live-scrape calls when IPFS backends are absent.
        Defaults to *False* to keep the function fast in offline / test
        environments.
    legal_vector_index_dir:
        Path to a directory that contains a pre-built legal corpus vector index
        (``legal_corpus.vectors.npy`` + ``legal_corpus.records.jsonl``).
        When ``None`` the function falls back to the
        ``COMPLAINT_LEGAL_VECTOR_INDEX_DIR`` environment variable.  If neither
        is set the semantic search pass is skipped.
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
    explicit_jurisdiction = resolve_explicit_jurisdiction(state)

    for index, assertion in enumerate(assertions or []):
        assertion_id = str(assertion.get("assertion_id") or assertion.get("id") or f"a-{index + 1}")
        text = str(assertion.get("text") or "").strip()
        if not text:
            ungrounded.append(assertion)
            details.append({"assertion_id": assertion_id, "grounded": False, "corpus_hits": []})
            continue

        corpus_hits: List[Dict[str, Any]] = []

        # Unresolved jurisdiction does not select federal or Oregon law.
        if explicit_jurisdiction == UNKNOWN_LEGAL_CONTEXT:
            details.append({
                "assertion_id": assertion_id,
                "text": text,
                "grounded": False,
                "applicability": UNKNOWN_LEGAL_CONTEXT,
                "reason": "unresolved_legal_context",
                "corpus_hits": [],
            })
            ungrounded.append({
                **assertion,
                "grounded": False,
                "applicability": UNKNOWN_LEGAL_CONTEXT,
                "corpus_hits": [],
            })
            continue

        # 1. Federal statutes only when federal jurisdiction was stated.
        if explicit_jurisdiction == "federal":
            try:
                hits = search_us_code(text, max_results=max_results_per_assertion)
                corpus_hits.extend(hits or [])
            except Exception:
                pass

        # 2. Federal Register only for an explicit federal jurisdiction.
        if explicit_jurisdiction == "federal" and not corpus_hits:
            try:
                hits = search_federal_register(text, max_results=max_results_per_assertion)
                corpus_hits.extend(hits or [])
            except Exception:
                pass

        # 3. State laws only for an explicit state code.
        if not corpus_hits and explicit_jurisdiction not in {UNKNOWN_LEGAL_CONTEXT, "federal"}:
            try:
                hits = search_state_laws(
                    text,
                    state=explicit_jurisdiction,
                    max_results=max_results_per_assertion,
                    allow_live_scrape_fallback=allow_live_scrape_fallback,
                )
                corpus_hits.extend(hits or [])
            except Exception:
                pass

        # 4. Semantic vector similarity search (optional, requires pre-built index)
        if not corpus_hits and _vector_index_dir:
            try:
                hits = _search_legal_vector_index(
                    text,
                    index_dir=_vector_index_dir,
                    max_results=max_results_per_assertion,
                )
                corpus_hits.extend(hits or [])
            except Exception:
                pass

        is_grounded = bool(corpus_hits)
        detail: Dict[str, Any] = {
            "assertion_id": assertion_id,
            "text": text,
            "grounded": is_grounded,
            "corpus_hits": corpus_hits[:max_results_per_assertion],
        }
        details.append(detail)
        if is_grounded:
            grounded.append({**assertion, "grounded": True, "corpus_hits": corpus_hits[:max_results_per_assertion]})
        else:
            ungrounded.append({**assertion, "grounded": False, "corpus_hits": []})

    total = len(assertions or [])
    grounded_count = len(grounded)
    corpus_coverage_percent = int(round((grounded_count / total) * 100)) if total else None

    return {
        "grounded": grounded,
        "ungrounded": ungrounded,
        "details": details,
        "grounded_count": grounded_count,
        "ungrounded_count": len(ungrounded),
        "total_assertion_count": total,
        "corpus_coverage_percent": corpus_coverage_percent,
        "jurisdiction": explicit_jurisdiction,
        "context_status": UNKNOWN_LEGAL_CONTEXT if explicit_jurisdiction == UNKNOWN_LEGAL_CONTEXT else "explicit",
        "selected_rule_applicability": UNKNOWN_LEGAL_CONTEXT,
    }


def search_legal_authority_program(
    program: Dict[str, Any],
    *,
    max_results: int = 5,
    state: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a normalized legal search program against matching authority families."""
    if not isinstance(program, dict):
        raise TypeError("program must be a dictionary")

    query = str(program.get("query_text") or "").strip()
    if not query:
        raise ValueError("program.query_text is required")

    families = {
        str(family or "").strip()
        for family in (program.get("authority_families") or [])
        if str(family or "").strip()
    }
    plan = legal_requirement_search_plan(program, state=state)
    jurisdiction = str(plan["jurisdiction"])
    state_code = str(plan["state_code"])

    results: Dict[str, List[Dict[str, Any]]] = {
        "statutes": [],
        "state_statutes": [],
        "regulations": [],
        "administrative_rules": [],
        "case_law": [],
        "docket_materials": [],
    }

    if plan["search_us_code"]:
        results["statutes"] = search_us_code(query, max_results=max_results)
    if plan["search_state_laws"]:
        results["state_statutes"] = search_state_laws(query, state=state_code, max_results=max_results)
    if plan["search_federal_register"]:
        results["regulations"] = search_federal_register(query, max_results=max_results)
    if plan["search_state_administrative_rules"]:
        results["administrative_rules"] = search_state_administrative_rules(query, state=state_code, max_results=max_results)
    if plan["search_case_law"] and ("case_law" in families or not families):
        results["case_law"] = search_recap_documents(query, max_results=max_results)
    if plan["search_case_law"] and ("docket_material" in families or not families):
        results["docket_materials"] = search_recap_documents(query, max_results=max_results)

    flat_results = [
        item
        for bucket in results.values()
        for item in bucket
        if isinstance(item, dict)
    ]
    return with_adapter_metadata(
        {
            "program": dict(program),
            "query": query,
            "authority_families": sorted(families),
            "results": results,
            "flat_results": flat_results,
            "result_count": len(flat_results),
        },
        operation="search_legal_authority_program",
        backend_available=True,
        implementation_status="normalized",
        extra_metadata={
            "program_id": str(program.get("program_id") or ""),
            "program_type": str(program.get("program_type") or ""),
            "authority_intent": str(program.get("authority_intent") or ""),
            "jurisdiction": jurisdiction,
            "state_code": state_code,
            "context_status": plan["context_status"],
            "selected_rule_applicability": plan["selected_rule_applicability"],
        },
    )


__all__ = [
    "LEGAL_SCRAPERS_AVAILABLE",
    "LEGAL_SCRAPERS_ERROR",
    "LEGAL_SOURCE_AVAILABILITY",
    "get_last_legal_search_diagnostic",
    "search_us_code",
    "search_federal_register",
    "search_recap_documents",
    "search_state_laws",
    "search_state_administrative_rules",
    "search_legal_authority_program",
    "constrain_assertions_to_corpus",
    "UNKNOWN_LEGAL_CONTEXT",
    "LEGAL_DATE_ROLES",
    "resolve_explicit_jurisdiction",
    "classify_legal_date",
    "empty_legal_context",
    "apply_legal_context_update",
    "questions_for_legal_context",
    "select_requirement_applicability",
    "legal_requirement_search_plan",
]
