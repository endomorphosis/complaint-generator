from __future__ import annotations

import os

# Legal discovery may use installed NLP assets, but must never bootstrap or
# download them during an optional backend import or a bounded corpus lookup.
os.environ["IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD"] = "0"

import asyncio
import calendar
import hashlib
import math
from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timezone
import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Union

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
# Bounded-only API resolution occurs inside the owned worker deadline.
_search_us_code_corpus_async, _us_code_corpus_error = None, None
# Bounded-only API resolution occurs inside the owned worker deadline.
_search_federal_register_corpus_async, _federal_register_corpus_error = None, None
# Bounded-only API resolution occurs inside the owned worker deadline.
_search_court_rules_corpus_async, _court_rules_corpus_error = None, None
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
    state_map = dict(_EXPLICIT_STATE_NAMES)
    if isinstance(_state_code_map, dict):
        for code, name in _state_code_map.items():
            label = str(name or "").strip().lower()
            if label:
                state_map.setdefault(label, str(code).upper())
    if len(state) == 2 and state.isalpha():
        code = state.upper()
        return code if code in set(state_map.values()) else fallback
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
    if _UNCERTAIN_DATE_RE.search(raw) or re.search(
        r"\b(?:or|not|unknown|unsure|whether|maybe|possibly)\b", raw, re.IGNORECASE
    ):
        parsed.update({
            "granularity": "uncertain_range",
            "precision": "uncertain_range",
            "is_range": True,
            "is_uncertain": True,
        })
        return parsed

    month_names = "|".join(_MONTH_NAME_TO_NUMBER)
    range_match = re.fullmatch(
        r"(?:from\s+)?(.+?)\s+(?:to|through|until|-)\s+(.+)",
        raw,
        flags=re.IGNORECASE,
    )
    if range_match and range_match.group(1).strip() and range_match.group(2).strip():
        start = _parse_explicit_legal_date(range_match.group(1).strip())
        end = _parse_explicit_legal_date(range_match.group(2).strip())
        first = start.get("start_date")
        last = end.get("end_date")
        if first and last and not start.get("is_uncertain") and not end.get("is_uncertain") and first <= last:
            parsed.update({
                "start_date": first,
                "end_date": last,
                "granularity": "range",
                "precision": "range",
                "is_range": True,
                "is_uncertain": bool(start.get("is_uncertain") or end.get("is_uncertain")),
            })
            return parsed
        parsed["is_uncertain"] = True
        return parsed

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:T\S+)?", raw)
    if iso_match:
        year, month, day = (int(item) for item in iso_match.groups())
        try:
            iso_date = date(year, month, day).isoformat()
            if "T" in raw:
                datetime.fromisoformat(raw)
        except ValueError:
            parsed["is_uncertain"] = True
            return parsed
        parsed.update({
            "precise_date": iso_date,
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "precision": "day",
        })
        return parsed

    month_day_year = re.fullmatch(
        rf"({month_names})\s+(\d{{1,2}}),\s*(\d{{4}})",
        raw,
        flags=re.IGNORECASE,
    )
    if month_day_year:
        month = _MONTH_NAME_TO_NUMBER[month_day_year.group(1).lower()]
        day = int(month_day_year.group(2))
        year = int(month_day_year.group(3))
        try:
            iso_date = date(year, month, day).isoformat()
        except ValueError:
            parsed["is_uncertain"] = True
            return parsed
        parsed.update({
            "precise_date": iso_date,
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "precision": "day",
        })
        return parsed

    month_year = re.fullmatch(rf"({month_names})\s+(\d{{4}})", raw, flags=re.IGNORECASE)
    if month_year:
        month = _MONTH_NAME_TO_NUMBER[month_year.group(1).lower()]
        year = int(month_year.group(2))
        if year < 1:
            parsed["is_uncertain"] = True
            return parsed
        start_date, end_date = _calendar_month_bounds(year, month)
        parsed.update({
            "start_date": start_date,
            "end_date": end_date,
            "granularity": "month",
            "precision": "month",
            "is_range": True,
        })
        return parsed

    year_match = re.fullmatch(r"(19\d{2}|20\d{2}|21\d{2})", raw)
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
    if isinstance(value, dict):
        raw_value = value.get("raw_text") if value.get("role") == role else ""
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


def _resolved_legal_date(record: Any) -> bool:
    """Reparse source text; serialized date labels cannot grant applicability."""
    classified = _parse_explicit_legal_date(_date_raw(record))
    return bool(classified.get("start_date") and classified.get("end_date") and not classified.get("is_uncertain"))


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
        if role == DATE_ROLE_EVENT and "event_dates" not in proposed:
            current["event_dates"] = [classified] if _date_raw(classified) else []

    if "event_dates" in proposed:
        event_dates = []
        for item in proposed.get("event_dates") or []:
            event_dates.append(classify_legal_date(item, role=DATE_ROLE_EVENT))
        prior_event_raws = [_date_raw(item) for item in (current.get("event_dates") or []) if _date_raw(item)]
        new_event_raws = [_date_raw(item) for item in event_dates if _date_raw(item)]
        if prior_event_raws != new_event_raws and (prior_event_raws or _context_has_selected_state(current, dependent_proof)):
            changed.append("event_dates")
        current["event_dates"] = event_dates
        aggregate = event_dates[0] if len(event_dates) == 1 else classify_legal_date("", role=DATE_ROLE_EVENT)
        if _date_raw(current.get("event_date")) != _date_raw(aggregate) and _context_has_selected_state(current, dependent_proof):
            changed.append(DATE_ROLE_EVENT)
        current["event_date"] = aggregate

    if changed:
        current["context_revision"] = int(current.get("context_revision") or 0) + 1
        current["changed_fields"] = list(dict.fromkeys(changed))
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
    jurisdiction = resolve_explicit_jurisdiction(legal_context.get("jurisdiction"))
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
        if isinstance(item, dict) and _resolved_legal_date(item)
    ]
    event_date = legal_context.get("event_date") if isinstance(legal_context.get("event_date"), dict) else {}
    if not event_dates and not _resolved_legal_date(event_date):
        questions.append({
            "question_id": "legal_context.event_dates",
            "field": "event_date",
            "prompt": (
                "What dates or date ranges are relevant to the events? "
                "If you know only a range, give the range. A single day will not be invented."
            ),
            "reason": "missing_event_dates",
        })
    # Rule-version selection needs one precise query day; a truthful range is
    # still retained, but must not silently close this clarification question.
    if (selecting_rules or _date_raw(legal_context.get("applicable_law_date"))) and not _parse_explicit_legal_date(_date_raw(legal_context.get("applicable_law_date"))).get("precise_date"):
        questions.append({
            "question_id": "legal_context.applicable_law_date",
            "field": "applicable_law_date",
            "prompt": "What date should be used to decide which version of the law applies?",
            "reason": "missing_applicable_law_date",
        })
    if selecting_rules and not _resolved_legal_date(legal_context.get("filing_reference_date")):
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
    applicable_law_date = classify_legal_date(context.get("applicable_law_date"), role=DATE_ROLE_APPLICABLE_LAW)
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
    if not _resolved_legal_date(applicable_law_date):
        return {
            "applicability": UNKNOWN_LEGAL_CONTEXT,
            "selected": False,
            "reason": "unresolved_applicable_law_date" if _date_raw(applicable_law_date) else "missing_applicable_law_date",
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


@dataclass(frozen=True)
class SourcedLegalRequirement:
    """One legal requirement that can be handed to DependencyGraphBuilder.

    String lists from SummaryJudgmentHook are not instances of this type.
    A user assertion never fills the authority fields.
    """

    claim_type: str
    name: str
    description: str
    authority_locator: str
    source_locator: str
    jurisdiction: str
    effective_date: str
    authority_version: str
    derivation_status: str
    proof_status: str
    unresolved_reason: str = ""
    asserted_text: str = ""
    source_record: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_builder_entry(self, *, legal_context: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Bind an entry to real source proof and the supplied current context."""
        # Inspect the bounded proof before making a recursive copy. Extra fields
        # carry the promoted span/hash/treatment record, not authority to replace
        # this object's source record or its closed status fields.
        payload = dict(self.extra or {})
        payload.update({item.name: getattr(self, item.name) for item in fields(self) if item.name != "extra"})
        payload["intake_requirement_status"] = "unresolved"
        payload["authority_source_locator"] = self.authority_locator or self.source_locator
        if _is_user_law_assertion(payload):
            payload.update(proof_status="not_authoritative", derivation_status="user_assertion",
                           unresolved_reason="user_assertion_cannot_create_law")
            return payload
        if self.unresolved_reason or self.proof_status == "not_authoritative":
            if self.proof_status != "not_authoritative":
                payload["proof_status"] = "unresolved"
            return payload
        reason, source, revision = _bind_requirement_current_context(payload, legal_context)
        if reason:
            payload.update(proof_status="unresolved", derivation_status="unresolved", unresolved_reason=reason)
        else:
            payload.update(source_record=source, context_revision=revision,
                           proof_status="source_bound", derivation_status="source_derived",
                           intake_requirement_status="source_bound")
        return payload


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _is_user_law_assertion(record: Mapping[str, Any]) -> bool:
    """User text cannot become authoritative law, even with a pasted citation."""
    if record.get("user_asserted") is True or record.get("authoritative") is False and record.get("origin") == "user":
        return True
    origin = _text(record.get("origin") or record.get("source_kind")).lower()
    if origin in {"user", "user_assertion", "complainant", "summary_judgment_hook"}:
        return True
    derivation = _text(record.get("derivation_status")).lower()
    return derivation in {"user_assertion", "user", "asserted"}


def _locator_from(record: Mapping[str, Any]) -> str:
    for key in ("authority_locator", "source_locator", "authority_source_locator", "citation", "uri", "authority_id"):
        text = _text(record.get(key))
        if text:
            return text
    source = record.get("source_record")
    if isinstance(source, Mapping):
        return _locator_from(source)
    return ""


def _version_from(record: Mapping[str, Any]) -> str:
    for key in ("authority_version", "version", "corpus_version"):
        text = _text(record.get(key))
        if text:
            return text
    source = record.get("source_record")
    if isinstance(source, Mapping):
        return _version_from(source)
    return ""


def _effective_date_from(record: Mapping[str, Any]) -> str:
    for key in ("effective_date", "applicable_date"):
        value = record.get(key)
        if isinstance(value, Mapping):
            text = _text(value.get("precise_date") or value.get("raw_text"))
        else:
            text = _text(value)
        if text:
            return text
    source = record.get("source_record")
    if isinstance(source, Mapping):
        return _effective_date_from(source)
    return ""


def _bind_requirement_current_context(record: Mapping[str, Any], legal_context: Optional[Mapping[str, Any]]):
    """Reuse DG's full source gate against an explicit current query context."""
    from complaint_phases.dependency_graph import DependencyGraphBuilder

    if not isinstance(legal_context, Mapping):
        return "missing_current_legal_context", None, None
    jurisdiction = resolve_explicit_jurisdiction(legal_context.get("jurisdiction"))
    if jurisdiction == UNKNOWN_LEGAL_CONTEXT:
        return "unresolved_current_jurisdiction", None, None
    current_date = classify_legal_date(legal_context.get("applicable_law_date"), role=DATE_ROLE_APPLICABLE_LAW)
    query_date = current_date.get("precise_date")
    if not query_date or current_date.get("is_uncertain"):
        return "missing_current_applicable_law_date", None, None
    revision = legal_context.get("context_revision", 0)
    if type(revision) is not int or revision < 0:
        return "invalid_current_context_revision", None, None
    prior_revision = record.get("context_revision")
    if prior_revision is not None and (type(prior_revision) is not int or prior_revision != revision):
        return "stale_legal_context", None, None
    if resolve_explicit_jurisdiction(record.get("jurisdiction")) != jurisdiction:
        return "jurisdiction_not_selected", None, None
    source = record.get("source_record")
    if not DependencyGraphBuilder._bounded_source_record(source):
        return "unverified_source_record", None, None
    previous_query = source.get("query_context") or source.get("temporal_query_context")
    if previous_query is not None and not isinstance(previous_query, dict):
        return "unverified_source_record", None, None
    for stored in (source.get("context_revision"), (previous_query or {}).get("context_revision")):
        if stored is not None and (type(stored) is not int or stored != revision):
            return "stale_legal_context", None, None
    # Re-derive every original proof field before consulting its query result.
    # Preserve the source's date provenance instead of changing an as_of_date
    # proof into a different explicit_query_context proof just to relabel it.
    if not DependencyGraphBuilder._is_verified_legal_requirement(record):
        return "unverified_source_record", None, None
    temporal = record.get("temporal_applicability")
    if (not isinstance(temporal, dict) or temporal.get("query_date") != query_date
            or resolve_explicit_jurisdiction(temporal.get("query_jurisdiction")) != jurisdiction):
        return "source_proof_not_bound_to_current_context", None, None
    return "", deepcopy(source), revision


def unresolved_legal_requirement(
    claim_type: str,
    reason: str,
    *,
    jurisdiction: str = UNKNOWN_LEGAL_CONTEXT,
    asserted_text: str = "",
    derivation_status: str = "unresolved",
    proof_status: str = "unresolved",
) -> SourcedLegalRequirement:
    """An explicit non-rule. Missing authority is not filled in."""
    resolved = resolve_explicit_jurisdiction(jurisdiction)
    return SourcedLegalRequirement(
        claim_type=str(claim_type or "unknown"),
        name="Unresolved legal requirement",
        description=(
            "No sourced legal requirement was selected. "
            "Missing or ambiguous authority is unresolved and was not replaced with an invented rule."
        ),
        authority_locator="",
        source_locator="",
        jurisdiction=resolved,
        effective_date="",
        authority_version="",
        derivation_status=derivation_status,
        proof_status=proof_status,
        unresolved_reason=reason,
        asserted_text=_text(asserted_text)[:500],
    )


def sourced_requirement_from_record(
    record: Mapping[str, Any],
    *,
    claim_type: str,
    legal_context: Optional[Mapping[str, Any]] = None,
) -> SourcedLegalRequirement:
    """Adapt one sourced mapping. Incomplete authority stays unresolved."""
    claim = _text(record.get("claim_type") or claim_type) or "unknown"
    if _is_user_law_assertion(record):
        return unresolved_legal_requirement(
            claim,
            "user_assertion_cannot_create_law",
            jurisdiction=record.get("jurisdiction") or UNKNOWN_LEGAL_CONTEXT,
            asserted_text=record.get("description") or record.get("name") or record.get("rule_text") or "",
            derivation_status="user_assertion",
            proof_status="not_authoritative",
        )
    source = record.get("source_record") if isinstance(record.get("source_record"), Mapping) else {}
    jurisdiction = resolve_explicit_jurisdiction(
        record.get("jurisdiction") or record.get("state") or source.get("jurisdiction") or source.get("state")
    )
    locator = _locator_from(record)
    source_locator = _text(record.get("source_locator") or record.get("source_span") or locator)
    effective_date = _effective_date_from(record)
    version = _version_from(record)
    reason = ""
    if not locator:
        reason = "missing_authority_locator"
    elif jurisdiction == UNKNOWN_LEGAL_CONTEXT:
        reason = "unresolved_jurisdiction"
    elif not effective_date or not version:
        reason = "missing_effective_date_or_version"
    if reason:
        unresolved = unresolved_legal_requirement(claim, reason, jurisdiction=jurisdiction)
        return unresolved
    preserved = {
        key: value for key, value in record.items()
        if key not in {
            "claim_type", "name", "description", "authority_locator", "source_locator",
            "jurisdiction", "effective_date", "authority_version", "derivation_status",
            "proof_status", "unresolved_reason", "asserted_text", "source_record", "extra",
        }
    }
    source_record = record.get("source_record") if isinstance(record.get("source_record"), dict) else None
    requirement = SourcedLegalRequirement(
        claim_type=claim,
        name=_text(record.get("name") or record.get("rule_id") or "Sourced requirement"),
        description=str(record.get("description") or record.get("rule_text") or ""),
        authority_locator=locator,
        source_locator=source_locator,
        jurisdiction=jurisdiction,
        effective_date=effective_date,
        authority_version=version,
        derivation_status="source_derived",
        proof_status="source_bound",
        source_record=source_record,
        extra=preserved,
    )
    entry = requirement.as_builder_entry(legal_context=legal_context)
    if entry["intake_requirement_status"] != "source_bound":
        return unresolved_legal_requirement(claim, entry["unresolved_reason"], jurisdiction=jurisdiction)
    return requirement


def _groups_from_requirements(requirements: Any) -> List[tuple]:
    """Normalize dict, typed, or SummaryJudgmentHook list[str] inputs."""
    if requirements is None:
        return []
    if isinstance(requirements, SourcedLegalRequirement):
        return [(requirements.claim_type, [requirements])]
    if isinstance(requirements, Mapping):
        groups = []
        for claim_type, items in requirements.items():
            if isinstance(items, (str, SourcedLegalRequirement, Mapping)):
                items = [items]
            elif not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
                items = [items]
            groups.append((str(claim_type), list(items)))
        return groups
    if isinstance(requirements, Sequence) and not isinstance(requirements, (str, bytes)):
        return [("unknown", list(requirements))]
    return [("unknown", [requirements])]


def adapt_sourced_legal_requirements(
    requirements: Any,
    *,
    legal_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Typed adapter from sourced requirements to DependencyGraphBuilder entries.

    ``SummaryJudgmentHook`` values are ``dict[str, list[str]]``. Those strings
    are recorded as unresolved requirements. They are not copied through as
    legal element text and they are not authoritative law.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for claim_type, items in _groups_from_requirements(requirements):
        entries = grouped.setdefault(str(claim_type or "unknown"), [])
        for item in items:
            if isinstance(item, SourcedLegalRequirement):
                requirement = item
            elif isinstance(item, str):
                requirement = unresolved_legal_requirement(
                    claim_type,
                    "summary_judgment_string_is_not_authority",
                    jurisdiction=(legal_context or {}).get("jurisdiction") if isinstance(legal_context, Mapping) else UNKNOWN_LEGAL_CONTEXT,
                    asserted_text=item,
                    derivation_status="unresolved",
                    proof_status="not_authoritative",
                )
            elif isinstance(item, Mapping):
                requirement = sourced_requirement_from_record(item, claim_type=claim_type, legal_context=legal_context)
            else:
                requirement = unresolved_legal_requirement(
                    claim_type,
                    "ambiguous_authority",
                    jurisdiction=(legal_context or {}).get("jurisdiction") if isinstance(legal_context, Mapping) else UNKNOWN_LEGAL_CONTEXT,
                )
            entries.append(requirement.as_builder_entry(legal_context=legal_context))
    return grouped


def intake_legal_selection(
    legal_context: Optional[Mapping[str, Any]],
    claim_candidates: Optional[Iterable[Any]],
) -> Dict[str, Any]:
    """Resolve jurisdiction, relevant date, and claim candidates before selection.

    Unknown jurisdiction stays the explicit value ``unknown``. This function
    does not search for law and does not invent a jurisdiction.
    """
    context = dict(legal_context) if isinstance(legal_context, Mapping) else empty_legal_context()
    jurisdiction = resolve_explicit_jurisdiction(context.get("jurisdiction"))
    context["jurisdiction"] = jurisdiction
    applicable = context.get("applicable_law_date") if isinstance(context.get("applicable_law_date"), Mapping) else {}
    relevant_date = ""
    if _resolved_legal_date(applicable) and not applicable.get("is_uncertain"):
        relevant_date = _text(applicable.get("precise_date"))
    candidates: List[Dict[str, Any]] = []
    for item in claim_candidates or []:
        if isinstance(item, str):
            claim_type = _text(item)
            record = {"claim_type": claim_type, "name": claim_type}
        elif isinstance(item, Mapping):
            claim_type = _text(item.get("claim_type") or item.get("type"))
            record = {"claim_type": claim_type, "name": _text(item.get("name") or item.get("label") or claim_type), "description": _text(item.get("description"))}
        else:
            continue
        if not claim_type or claim_type.lower() == "unknown":
            continue
        candidates.append(record)
    questions = questions_for_legal_context(context, selecting_rules=True)
    if not candidates:
        questions.append({
            "question_id": "legal_context.claim_candidates",
            "field": "claim_candidates",
            "prompt": (
                "Which claim should be checked against sourced law? "
                "Name the claim. A claim will not be inferred in order to invent legal requirements."
            ),
            "reason": "missing_claim_candidates",
        })
    reasons = []
    if jurisdiction == UNKNOWN_LEGAL_CONTEXT:
        reasons.append("unresolved_jurisdiction")
    if not relevant_date:
        reasons.append("missing_applicable_law_date")
    if not candidates:
        reasons.append("missing_claim_candidates")
    ready = not reasons
    return {
        "ready_to_select": ready,
        "selection_status": "ready" if ready else "unresolved_context",
        "jurisdiction": jurisdiction,
        "relevant_date": relevant_date or None,
        "claim_candidates": candidates,
        "questions": [] if ready else questions,
        "unresolved_reasons": reasons,
    }


_ACQUISITION_QUERY_TERM_CAP = 12
_ACQUISITION_TARGET_CAP = 16
_ACQUISITION_RESULT_CAP = 25
_ACQUISITION_TIMEOUT_CAP_SECONDS = 30.0


def _explicit_jurisdiction_token(value: Any) -> str:
    """Normalize an already-explicit code. Ambiguous text is left unchanged."""
    text = " ".join(str(value or "").split())
    prefixed = re.fullmatch(r"US-([A-Za-z]{2})", text)
    if not prefixed:
        return text
    code = prefixed.group(1).upper()
    if code in set(_EXPLICIT_STATE_NAMES.values()):
        return code
    return text


def _supported_claim_record(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """A selected claim is supported only when the intake registry names it."""
    from complaint_phases.intake_claim_registry import CLAIM_INTAKE_REQUIREMENTS, normalize_claim_type

    claim_type = _text(record.get("claim_type") or record.get("type"))
    normalized = normalize_claim_type(claim_type)
    if not normalized or normalized == "unknown" or normalized not in CLAIM_INTAKE_REQUIREMENTS:
        return None
    registry = CLAIM_INTAKE_REQUIREMENTS[normalized]
    return {
        "claim_type": normalized,
        "name": _text(record.get("name") or record.get("label") or registry.get("label") or normalized),
        "requirement_elements": [
            {
                "requirement_id": _text(element.get("element_id")),
                "label": _text(element.get("label")),
            }
            for element in (registry.get("elements") or [])
            if isinstance(element, Mapping) and _text(element.get("element_id"))
        ],
    }


def _classified_role(context: Mapping[str, Any], role: str) -> Dict[str, Any]:
    return classify_legal_date(context.get(role), role=role)


def _public_query_terms(
    *groups: Any,
    narrative: str,
) -> List[str]:
    """Keep short public-law terms. The case narrative is not a query."""
    narrative_text = " ".join(str(narrative or "").split())
    terms: List[str] = []
    seen = set()
    for group in groups:
        values = group if isinstance(group, (list, tuple)) else [group]
        for value in values:
            text = _text(value)
            if not text or len(text) > 80:
                continue
            if narrative_text and (text == narrative_text or (len(text) > 40 and text in narrative_text)):
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(text)
            if len(terms) >= _ACQUISITION_QUERY_TERM_CAP:
                return terms
    return terms


def _closed_corpus_plan(jurisdiction: str, authority_families: Optional[Iterable[Any]]) -> Dict[str, Any]:
    """Search flags follow the explicit jurisdiction. Unknown stays closed."""
    program: Dict[str, Any] = {"jurisdiction": jurisdiction}
    families = [_text(family) for family in (authority_families or []) if _text(family)]
    if families:
        program["authority_families"] = families
    plan = legal_requirement_search_plan(program, state=jurisdiction if jurisdiction != UNKNOWN_LEGAL_CONTEXT else None)
    plan["default_applied"] = False
    plan["guessed_jurisdiction"] = False
    return plan


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
        # Discovery in an explicitly selected state is allowed. A retrieved
        # court document still confers neither federal jurisdiction nor rule
        # applicability; those remain separate context-admission decisions.
        "search_case_law": (search_federal or search_state) and (include_all or "case_law" in families or "docket_material" in families),
        "authority_families": sorted(families),
    }


def _plan_searches_court_rules(plan: Dict[str, Any], families: set[str]) -> bool:
    """Court rules are opt-in and stay off the LAW01 plan equality contract.

    An empty family list must not start a corpus call. Request labels are not
    proof that a returned row matches the requested jurisdiction.
    """
    jurisdiction = str(plan.get("jurisdiction") or "")
    state_code = str(plan.get("state_code") or "")
    explicit = jurisdiction == "federal" or bool(state_code)
    return explicit and "court_rule" in families

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
    or _us_code_corpus_error
    or _federal_register_corpus_error
    or _court_rules_corpus_error
)

# Bounded corpus lookup. These labels are request intent only; a returned row
# still has to carry its own source jurisdiction, passage, and provenance.
CORPUS_FAMILY_US_CODE = "us_code"
CORPUS_FAMILY_STATE_STATUTE = "state_statute"
CORPUS_FAMILY_STATE_ADMIN = "state_administrative_rule"
CORPUS_FAMILY_FEDERAL_REGISTER = "federal_register"
CORPUS_FAMILY_COURT_RULE = "court_rule"
BOUNDED_CORPUS_FAMILIES = (
    CORPUS_FAMILY_US_CODE,
    CORPUS_FAMILY_STATE_STATUTE,
    CORPUS_FAMILY_STATE_ADMIN,
    CORPUS_FAMILY_FEDERAL_REGISTER,
    CORPUS_FAMILY_COURT_RULE,
)
RETRIEVAL_MODE_CACHE = "cache"
RETRIEVAL_MODE_OFFLINE = "offline"
RETRIEVAL_MODE_LIVE = "live"
BOUNDED_RETRIEVAL_MODES = (
    RETRIEVAL_MODE_CACHE,
    RETRIEVAL_MODE_OFFLINE,
    RETRIEVAL_MODE_LIVE,
)
_BOUNDED_RESULT_CAP = 25
_BOUNDED_TIMEOUT_CAP_SECONDS = 30.0
_SNIPPET_CHAR_CAP = 320
UNKNOWN_PROVENANCE = "unknown"

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
) -> Dict[str, Any]:
    """Defer legacy semantic lookup until an owned, privacy-bound API exists.

    A local index does not establish a local embedding provider. Neither index
    files nor assertion text are passed to the ambient embedding router here.
    """
    return _bounded_envelope(
        status="unavailable", family="legal_corpus", retrieval_mode="offline",
        capability="owned_vector_lookup_unavailable", error_code="owned_vector_lookup_unavailable",
        error_message="Legacy semantic corpus lookup has no owned private retrieval capability.",
    )


# LAW03 has no bound entailment prover. Caller labels and model output are not proof.
ENTAILMENT_PROVER_INTEGRATION = "unsupported"
_CONSTRAINT_CALLER_LABELS = (
    "grounded",
    "entailed",
    "entails",
    "source_verified",
    "applicable",
    "fact_verified",
    "verified",
    "legal_grounding",
)
_FACTUAL_ASSERTION_KINDS = {
    "fact",
    "factual",
    "factual_allegation",
    "user_fact",
    "user_assertion",
}


def _constraint_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _recognize_citations(text: str) -> List[Any]:
    """Regex citation recognition. A match is not source verification.

    The pinned extractor is
    ``ipfs_datasets_py.processors.legal_data.citation_extraction.extract_citations_from_text``.
    Positions are character offsets and URLs are generated references.
    """
    try:
        from ipfs_datasets_py.processors.legal_data.citation_extraction import (
            extract_citations_from_text,
        )
    except Exception:
        return []
    try:
        return list(extract_citations_from_text(text) or [])
    except Exception:
        return []


def _is_similarity_authority_hit(hit: Dict[str, Any], backend: str) -> bool:
    """Vector and similarity edges are not legal authority.

    The state-law adjacency contract labels this
    ``similarity_cannot_establish_legal_authority``. Those labels stay in place.
    """
    if backend == "legal_vector_index":
        return True
    edge = _constraint_text(hit.get("edge_class") or hit.get("edge_kind")).casefold()
    if "similar" in edge:
        return True
    if hit.get("similarity_cannot_establish_legal_authority") is True:
        return True
    authority = _constraint_text(hit.get("authority") or hit.get("authority_label")).casefold()
    if authority in {"similarity", "non_authoritative", "similarity_not_legal_authority"}:
        return True
    source = _constraint_text(hit.get("source") or hit.get("retrieval_backend")).casefold()
    if source in {"vector_index", "legal_vector_index"}:
        return True
    return False


def _citation_maps_to_assertion(assertion_text: str, citation: str) -> bool:
    left = _constraint_text(assertion_text).casefold()
    right = _constraint_text(citation).casefold()
    return bool(left and right and right in left)


def _court_text(value: Any) -> str:
    if isinstance(value, dict):
        return _constraint_text(value.get("court") or value.get("name"))
    return _constraint_text(value)


def _version_covers_applicable_date(hit: Dict[str, Any], applicable_law_date: Dict[str, Any]) -> tuple[str, str]:
    """Map a retrieved row onto the explicit applicable-law date.

    Missing version or effective date stays unknown. It does not mean the rule
    is inapplicable or that no law exists.
    """
    version = hit.get("corpus_version")
    if not isinstance(version, str) or not version.strip():
        return "unknown", "missing_rule_version"
    effective_raw = hit.get("effective_date")
    if not isinstance(effective_raw, str) or not effective_raw.strip():
        return "unknown", "missing_rule_version"
    effective = _parse_explicit_legal_date(effective_raw)
    if not effective.get("start_date") or effective.get("is_uncertain"):
        return "unknown", "unparsed_effective_date"
    law_start = applicable_law_date.get("start_date")
    law_end = applicable_law_date.get("end_date")
    if not law_start or not law_end:
        return "unknown", "missing_applicable_law_date"
    if law_end < effective["start_date"]:
        return "not_applicable", "effective_after_applicable_date"
    if law_start < effective["start_date"] <= law_end:
        return "unknown", "date_range_crosses_rule_version"
    # A single effective date starts a version. It is not a one-day version
    # unless the row also carries a sunset or repeal date.
    sunset_raw = hit.get("sunset_date") or hit.get("repealed_date") or hit.get("effective_end")
    rule_end = None
    if isinstance(sunset_raw, str) and sunset_raw.strip():
        sunset = _parse_explicit_legal_date(sunset_raw)
        if not sunset.get("end_date") or sunset.get("is_uncertain"):
            return "unknown", "unparsed_effective_date"
        rule_end = sunset.get("end_date")
    if rule_end and law_start > rule_end:
        return "not_applicable", "version_expired"
    if rule_end and law_start <= rule_end < law_end:
        return "unknown", "date_range_crosses_rule_version"
    return "in_force", "versioned_rule_mapping"


def _classify_constraint_hit(
    hit: Dict[str, Any],
    *,
    assertion_text: str,
    backend: str,
    jurisdiction: str,
    applicable_law_date: Dict[str, Any],
    court: str,
    expected_version: str,
) -> Dict[str, Any]:
    """Classify one retrieved row without promoting it to proof."""
    similarity = _is_similarity_authority_hit(hit, backend)
    normalized = normalize_corpus_candidate(
        hit,
        source_family=str(hit.get("source_family") or hit.get("type") or backend or "legal_corpus"),
        retrieval_mode="constraint",
        requested_jurisdiction=jurisdiction,
    )
    reasons: List[str] = []
    if similarity:
        reasons.append("similarity_not_legal_authority")
        normalized["authority_label"] = "similarity_not_legal_authority"
        normalized["similarity_cannot_establish_legal_authority"] = True
    passage_ok = (
        normalized.get("passage_status") == "full_text"
        and bool(normalized.get("source_passage"))
        and normalized.get("content_hash_scope") == "source_passage"
        and bool(normalized.get("content_hash"))
        and not normalized.get("content_hash_mismatch")
        and normalized.get("provenance_status") == "present"
        and bool(normalized.get("corpus_version"))
    )
    source_verified = bool(passage_ok and not similarity and normalized.get("citation_status") == "source")
    if not normalized.get("source_passage"):
        reasons.append("absent_source_passage")
    if normalized.get("content_hash_mismatch"):
        reasons.append("content_hash_mismatch")
    if normalized.get("uri_status") == "unverified_generated":
        reasons.append("generated_reference_url")
    if normalized.get("passage_status") == "snippet_only":
        reasons.append("snippet_only")

    citation = str(normalized.get("citation") or "")
    mapped = _citation_maps_to_assertion(assertion_text, citation)
    if not mapped:
        reasons.append("no_versioned_rule_mapping")
    hit_court = _court_text(hit.get("court"))
    if not court:
        reasons.append("missing_court_context")
    elif not hit_court:
        reasons.append("missing_source_court")
    elif hit_court.casefold() != court.casefold():
        reasons.append("court_mismatch")
    if normalized.get("jurisdiction_status") == "mismatch":
        reasons.append("jurisdiction_mismatch")
    elif normalized.get("jurisdiction") == UNKNOWN_LEGAL_CONTEXT:
        reasons.append("unknown_source_jurisdiction")
    if expected_version and str(normalized.get("corpus_version") or "") != expected_version:
        reasons.append("version_mismatch")
    version_state, version_reason = _version_covers_applicable_date(normalized, applicable_law_date)
    if version_reason != "versioned_rule_mapping":
        reasons.append(version_reason)

    blocking = {
        "similarity_not_legal_authority",
        "absent_source_passage",
        "content_hash_mismatch",
        "no_versioned_rule_mapping",
        "missing_court_context",
        "missing_source_court",
        "court_mismatch",
        "jurisdiction_mismatch",
        "unknown_source_jurisdiction",
        "version_mismatch",
        "missing_rule_version",
        "unparsed_effective_date",
        "effective_after_applicable_date",
        "version_expired",
        "date_range_crosses_rule_version",
        "missing_applicable_law_date",
        "snippet_only",
    }
    # A conflict is about this candidate only. It is not a finding that no law applies.
    hard_conflict = {
        "jurisdiction_mismatch",
        "court_mismatch",
        "version_mismatch",
        "effective_after_applicable_date",
        "version_expired",
    }
    if any(reason in hard_conflict for reason in reasons) or version_state == "not_applicable":
        applicability = "not_applicable"
    elif not source_verified or any(reason in blocking for reason in reasons):
        applicability = UNKNOWN_LEGAL_CONTEXT
    else:
        applicability = "applicable"

    normalized.update({
        "retrieval_backend": backend,
        "retrieved_candidate": True,
        "source_verified": source_verified,
        "source_verification": "verified" if source_verified else "unverified",
        "applicability": applicability,
        "applicable": applicability == "applicable",
        "entailment": ENTAILMENT_PROVER_INTEGRATION,
        "entails": False,
        "score_is_not_proof": True,
        "disposition_reasons": list(dict.fromkeys(reasons)),
    })
    return normalized


def _constraint_retrieval_status(attempts: List[Dict[str, Any]], hit_count: int) -> str:
    errors = [item for item in attempts if item.get("status") in {"backend_error", "timeout", "unavailable"}]
    timeouts = [item for item in attempts if item.get("status") == "timeout"]
    if any(item.get("status") == "skipped" for item in attempts) and not errors and hit_count == 0:
        return UNKNOWN_LEGAL_CONTEXT
    if hit_count and errors:
        return "partial"
    if hit_count:
        return "candidate"
    if timeouts and not any(item.get("status") == "backend_error" for item in attempts):
        return "timeout"
    if errors:
        return "unavailable" if all(item.get("status") == "unavailable" for item in errors) else "backend_error"
    if any(item.get("status") == "ok" for item in attempts):
        return "empty"
    return UNKNOWN_LEGAL_CONTEXT


def _invoke_constraint_backend(
    backend: str,
    fn: Callable[[], Any],
    attempts: List[Dict[str, Any]],
    collected: List[Dict[str, Any]],
) -> None:
    try:
        rows = fn()
    except TimeoutError:
        attempts.append({"backend": backend, "status": "timeout", "error_code": "timeout"})
        return
    except Exception:
        attempts.append({"backend": backend, "status": "backend_error", "error_code": "backend_error"})
        return
    if isinstance(rows, dict):
        status = rows.get("status")
        if type(status) is not str or status not in {"success", "empty", "partial_success"} or rows.get("bounded") is not True:
            outcome = "timeout" if status == "timeout" else ("unavailable" if status == "unavailable" else "backend_error")
            attempts.append({"backend": backend, "status": outcome,
                             "error_code": "backend_unavailable" if outcome == "unavailable" else outcome})
            return
        envelope = rows
        rows = envelope.get("results")
        if status == "partial_success":
            attempts.append({"backend": backend, "status": "backend_error", "error_code": "partial_result"})
    if not isinstance(rows, list):
        attempts.append({"backend": backend, "status": "backend_error", "error_code": "malformed_result"})
        return
    attempts.append({"backend": backend, "status": "ok", "result_count": len(rows)})
    for row in rows:
        if isinstance(row, dict):
            tagged = dict(row)
            tagged["_constraint_backend"] = backend
            collected.append(tagged)


def _bounded_envelope(
    *,
    status: str,
    family: str,
    retrieval_mode: str,
    capability: str = "",
    error_code: str = "",
    error_message: str = "",
    timeout_seconds: Optional[float] = None,
    attempted_backends: Optional[List[str]] = None,
    results: Optional[List[Dict[str, Any]]] = None,
    network_used: Optional[bool] = False,
    setup_invoked: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": status,
        "source_family": family,
        "retrieval_mode": retrieval_mode,
        "capability": capability,
        "error_code": error_code,
        "error_message": error_message,
        "timeout_seconds": timeout_seconds,
        "attempted_backends": list(attempted_backends or []),
        "results": list(results or []),
        "result_count": len(results or []),
        "bounded": capability != "cleanup_unconfirmed",
        "network_used": network_used,
        "setup_invoked": bool(setup_invoked),
        "applicability": UNKNOWN_LEGAL_CONTEXT,
        "selected_rule_applicability": UNKNOWN_LEGAL_CONTEXT,
    }
    if extra:
        payload.update(extra)
    return payload


# Fixed code is executed in isolated child interpreters; query/vector data travels
# only over stdin. The manager is a Linux subreaper, not an application-wide
# signal handler or subreaper. It owns cleanup of the actual upstream call tree.
_CORPUS_CALL_SOURCE = r"""
import asyncio, ctypes, importlib, json, os, signal, sys
request = json.loads(sys.stdin.buffer.read(1048577))
if request.get('schema') != 'complaint-legal-corpus-call@1': raise SystemExit(2)
# Match the actual manager around PDEATHSIG, including ancestor-subreaper
# adoption; checking only getppid()==1 would miss that case.
manager = request.get('expected_manager_pid')
if type(manager) is not int or manager <= 1 or os.getppid() != manager: raise SystemExit(2)
if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0: raise SystemExit(2)
if os.getppid() != manager: raise SystemExit(2)
roots = request['roots']
if not isinstance(roots,list) or not all(isinstance(p,str) for p in roots): raise SystemExit(2)
sys.path[:0] = roots
apis = {
 'us_code_corpus': ('ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api','search_us_code_corpus_from_parameters',False),
 'state_statute_corpus': ('ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api','search_state_law_corpus_from_parameters',False),
 'state_admin_corpus': ('ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api','search_state_law_corpus_from_parameters',False),
 'federal_register_corpus': ('ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api','search_federal_register_corpus_from_parameters',False),
 'court_rules_corpus': ('ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api','search_court_rules_corpus_from_parameters',False),
 'federal_register_direct': ('ipfs_datasets_py.processors.legal_scrapers.federal_scrapers.federal_register_scraper','search_federal_register',True),
 'local_us_code_index': ('ipfs_datasets_py.processors.legal_scrapers.federal_scrapers.us_code_scraper','search_us_code',True),
}
try:
 module, attribute, keywords = apis[request['api']]
 target = getattr(importlib.import_module(module), attribute)
 value = target(**request['parameters']) if keywords else target(request['parameters'])
 if not asyncio.iscoroutine(value): raise TypeError()
 result = asyncio.run(value)
 encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',',':')).encode()
 if len(encoded)>524288: raise ValueError()
 sys.stdout.buffer.write(encoded);sys.stdout.buffer.flush()
except (ImportError, AttributeError, FileNotFoundError):
 sys.stdout.buffer.write(b'{"status":"unavailable","error":"legal_backend_unavailable"}');sys.stdout.buffer.flush()
except BaseException:
 sys.stdout.buffer.write(b'{"status":"error","error":"legal_backend_failed"}');sys.stdout.buffer.flush()
"""
_CORPUS_MANAGER_SOURCE = r"""
import ctypes, errno, json, os, selectors, signal, subprocess, sys, time
# This isolated manager, never the application process, adopts orphaned call descendants.
if sys.platform != 'linux': raise SystemExit(2)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0: raise SystemExit(2)
request = json.loads(sys.stdin.buffer.read(1048577))
call_source = CALL_SOURCE_LITERAL
cancelled = False
process = None
cleanup_confirmed = False
def cancel(_signal, _frame):
 global cancelled
 cancelled = True
signal.signal(signal.SIGTERM,cancel)
signal.signal(signal.SIGINT,cancel)
def cleanup():
 # First stop the sole call group. Then reap its adopted descendants, including
 # an upstream subprocess left behind when an AnyIO worker's parent exits.
 if process is not None:
  try: os.killpg(process.pid,signal.SIGKILL)
  except ProcessLookupError: pass
  except OSError: return False
  try: process.wait(timeout=.25)
  except subprocess.TimeoutExpired: return False
 deadline=time.monotonic()+.75
 while time.monotonic()<deadline:
  try:
   children=[int(p) for p in open('/proc/self/task/'+str(os.getpid())+'/children').read().split()]
  except (OSError,ValueError): return False
  for pid in children:
   # A direct, unreaped child cannot have its PID reused until this manager waits.
   try: os.kill(pid,signal.SIGKILL)
   except ProcessLookupError: pass
  try:
   while True:
    pid,_=os.waitpid(-1,os.WNOHANG)
    if pid==0: break
  except ChildProcessError:
   return True
  time.sleep(.005)
 return False
result={'outcome':'error','cleanup_confirmed':False}
try:
 deadline=time.monotonic()+float(request['timeout_seconds'])
 call=dict(request['call']);call['expected_manager_pid']=os.getpid()
 raw=json.dumps(call,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
 process=subprocess.Popen([sys.executable,'-I','-c',call_source],stdin=subprocess.PIPE,
  stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ),process_group=0)
 process.stdin.write(raw);process.stdin.close()
 selector=selectors.DefaultSelector()
 for stream in (process.stdout,process.stderr):
  os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ)
 output=bytearray();total=0
 outcome='ok'
 while selector.get_map():
  if cancelled: outcome='cancelled';break
  remaining=deadline-time.monotonic()
  if remaining<=0: outcome='timeout';break
  for key,_ in selector.select(min(.02,remaining)):
   chunk=os.read(key.fileobj.fileno(),65536)
   if not chunk: selector.unregister(key.fileobj);continue
   total+=len(chunk)
   if total>524288: outcome='output_limit';break
   if key.fileobj is process.stdout: output.extend(chunk)
  if outcome!='ok':break
 result={'outcome':outcome,'cleanup_confirmed':False}
 if outcome=='ok':
  try:result['payload']=json.loads(output)
  except (ValueError,UnicodeError):result={'outcome':'error','cleanup_confirmed':False}
except BaseException:
 result={'outcome':'error','cleanup_confirmed':False}
finally:
 cleanup_confirmed=cleanup()
 result['cleanup_confirmed']=cleanup_confirmed
 if result.get('outcome')=='ok' and process is not None and process.returncode!=0:
  result={'outcome':'error','cleanup_confirmed':cleanup_confirmed}
 if not cleanup_confirmed:result={'outcome':'cleanup_unconfirmed','cleanup_confirmed':False}
 for stream in (() if process is None else (process.stdin,process.stdout,process.stderr)):
  try:stream.close()
  except (OSError,ValueError):pass
 sys.stdout.write(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')))
 sys.stdout.flush()
"""

def _owned_corpus_roots() -> List[str]:
    import site
    import sys
    from pathlib import Path
    from .loader import get_repo_paths
    paths = get_repo_paths()
    roots = []
    # Prefer the first-party vendored-source registry even on a cold process.
    # Installed copies must not silently replace an absent vendored dependency.
    registered = {"ipfs_datasets_py": paths.ipfs_datasets_repo,
                  "ipfs_accelerate_py": paths.ipfs_accelerate_repo,
                  "ipfs_kit_py": paths.ipfs_kit_repo}
    datasets_present = False
    for package, candidate in registered.items():
        root = Path(candidate).resolve() if candidate is not None else None
        if root is not None and (root / package / "__init__.py").is_file():
            roots.append(str(root))
            datasets_present = datasets_present or package == "ipfs_datasets_py"
            continue
        # A source qualification may explicitly import another checked-out
        # dependency. Accept that source checkout, never an installed package.
        loaded = sys.modules.get(package)
        source = getattr(loaded, "__file__", None)
        if source:
            root = Path(source).resolve().parent.parent
            if root.name == package and (root / ".git").exists() and (root / package / "__init__.py").is_file():
                roots.append(str(root))
                datasets_present = datasets_present or package == "ipfs_datasets_py"
    if not datasets_present:
        return []
    for root in site.getsitepackages():
        if Path(root).is_dir() and root not in roots:
            roots.append(root)
    return roots


def _run_owned_deadline(api: str, parameters: Dict[str, Any], timeout_seconds: float) -> tuple[str, Any]:
    """Bound cold imports, an upstream call, output and its descendant cleanup.

    Unsupported custody is unavailable. In particular an async wrapper is not
    treated as cancellation of an upstream blocking subprocess.
    """
    import json
    import os
    import signal
    import subprocess
    import sys
    if sys.platform != "linux":
        return "custody_unavailable", None
    roots = _owned_corpus_roots()
    if not roots:
        return "custody_unavailable", None
    call = {"schema": "complaint-legal-corpus-call@1", "api": api,
            "parameters": parameters, "roots": roots}
    try:
        encoded = json.dumps({"call": call, "timeout_seconds": timeout_seconds},
                             ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError):
        return "invalid_parameters", None
    if len(encoded) > 1048576:
        return "invalid_parameters", None
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL") if key in os.environ}
    environment.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                        "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0", "IPFS_DATASETS_PY_MINIMAL_IMPORTS": "1",
                        "IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD": "0",
                        "PYTHONDONTWRITEBYTECODE": "1"})
    source = _CORPUS_MANAGER_SOURCE.replace("CALL_SOURCE_LITERAL", repr(_CORPUS_CALL_SOURCE), 1)
    process = None
    try:
        process = subprocess.Popen([sys.executable, "-I", "-c", source],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=environment, start_new_session=True)
        output, _ = process.communicate(encoded, timeout=timeout_seconds + 1.5)
        if process.returncode != 0 or len(output) > 600000:
            return "cleanup_unconfirmed", None
        result = json.loads(output)
        if not isinstance(result, dict) or result.get("cleanup_confirmed") is not True:
            return "cleanup_unconfirmed", None
        outcome = result.get("outcome")
        return (outcome, result.get("payload")) if outcome in {"ok", "timeout", "cancelled", "output_limit", "error"} else ("error", None)
    except subprocess.TimeoutExpired:
        # The manager handles SIGTERM by cancelling the owned call and reaping.
        process.send_signal(signal.SIGTERM)
        try:
            process.communicate(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=.25)
        return "cleanup_unconfirmed", None
    except BaseException as exc:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:process.communicate(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=.25)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return ("cleanup_unconfirmed" if process is not None else "custody_unavailable"), None


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clip_snippet(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= _SNIPPET_CHAR_CAP:
        return text
    return text[:_SNIPPET_CHAR_CAP].rstrip()


def _independent_text(item: Dict[str, Any], *keys: str) -> tuple[str, bool]:
    """Return a source string only when the field is an actual string.

    Non-strings are corrupted provenance, not empty values we may invent.
    """
    for key in keys:
        if key not in item:
            continue
        value = item.get(key)
        if isinstance(value, str):
            return value.strip(), False
        if value is None:
            continue
        return "", True
    return "", False


def normalize_corpus_candidate(
    item: Any,
    *,
    source_family: str,
    retrieval_mode: str,
    requested_jurisdiction: str = "",
    requested_state: str = "",
    publication_filter: Optional[Dict[str, str]] = None,
    retrieved_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize one corpus row without treating the request as proof."""
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    base = {
        "source_family": source_family,
        "source_type": source_family,
        "uri": "",
        "uri_status": "missing",
        "citation": "",
        "citation_status": "missing",
        "content_hash": "",
        "content_hash_scope": "unavailable",
        "corpus_id": None,
        "corpus_version": None,
        "cid": None,
        "retrieved_at": retrieved,
        "source_passage": "",
        "snippet": "",
        "passage_status": "missing",
        "jurisdiction": UNKNOWN_LEGAL_CONTEXT,
        "jurisdiction_status": UNKNOWN_PROVENANCE,
        "publication_date": None,
        "publication_date_status": UNKNOWN_PROVENANCE,
        "effective_date": None,
        "effective_date_status": UNKNOWN_PROVENANCE,
        "provenance_status": "missing",
        "applicability": UNKNOWN_LEGAL_CONTEXT,
        "candidate_status": "candidate",
        "retrieval_mode": retrieval_mode,
        "publication_filter_is_not_effective_date": bool(publication_filter),
    }
    if not isinstance(item, dict):
        base["provenance_status"] = "corrupted"
        return base

    corrupted = False
    passage, passage_bad = _independent_text(item, "source_passage", "text", "content", "full_text", "section_text")
    snippet, snippet_bad = _independent_text(item, "snippet", "summary", "excerpt")
    corrupted = corrupted or passage_bad or snippet_bad
    if passage:
        base["source_passage"] = passage
        base["passage_status"] = "full_text"
        base["content_hash"] = _sha256_text(passage)
        base["content_hash_scope"] = "source_passage"
        clipped = _clip_snippet(snippet or passage)
        if clipped == passage and len(passage) > _SNIPPET_CHAR_CAP:
            clipped = passage[:_SNIPPET_CHAR_CAP].rstrip()
        if clipped == passage:
            # A snippet must stay distinct from the full passage.
            base["snippet"] = ""
        else:
            base["snippet"] = clipped
    elif snippet:
        base["snippet"] = _clip_snippet(snippet)
        base["passage_status"] = "snippet_only"
        base["content_hash"] = _sha256_text(base["snippet"])
        base["content_hash_scope"] = "snippet"
        base["source_passage"] = ""

    uri, uri_bad = _independent_text(item, "uri", "url", "source_url", "html_url", "absolute_url")
    generated, generated_bad = _independent_text(item, "generated_url", "reference_url")
    corrupted = corrupted or uri_bad or generated_bad
    if uri:
        base["uri"] = uri
        base["uri_status"] = "source"
    elif generated:
        base["uri"] = generated
        base["uri_status"] = "unverified_generated"

    citation, citation_bad = _independent_text(
        item, "citation", "document_number", "section_number", "rule_number", "identifier"
    )
    corrupted = corrupted or citation_bad
    if citation:
        base["citation"] = citation
        base["citation_status"] = "source"

    for source_key, target_key in (
        ("corpus_id", "corpus_id"),
        ("hf_dataset_id", "corpus_id"),
        ("dataset_id", "corpus_id"),
    ):
        value = item.get(source_key)
        if isinstance(value, str) and value.strip() and base["corpus_id"] is None:
            base["corpus_id"] = value.strip()
        elif source_key in item and value not in (None, "") and not isinstance(value, str):
            corrupted = True
    version = item.get("corpus_version", item.get("release", item.get("revision")))
    if isinstance(version, str) and version.strip():
        base["corpus_version"] = version.strip()
    elif version not in (None, ""):
        corrupted = True
    cid = item.get("cid")
    if isinstance(cid, str) and cid.strip():
        base["cid"] = cid.strip()
    elif cid not in (None, ""):
        corrupted = True

    supplied_hash = item.get("content_hash")
    if isinstance(supplied_hash, str) and supplied_hash.strip():
        if base["content_hash"] and supplied_hash.strip() != base["content_hash"]:
            corrupted = True
            base["content_hash_mismatch"] = True
    elif supplied_hash not in (None, ""):
        corrupted = True

    row_jurisdiction, jurisdiction_bad = _independent_text(item, "jurisdiction", "state", "state_code")
    corrupted = corrupted or jurisdiction_bad
    if row_jurisdiction:
        resolved = resolve_explicit_jurisdiction(row_jurisdiction)
        base["jurisdiction"] = resolved
        requested = resolve_explicit_jurisdiction(requested_state or requested_jurisdiction)
        if requested == UNKNOWN_LEGAL_CONTEXT:
            base["jurisdiction_status"] = "source"
        elif resolved != requested:
            base["jurisdiction_status"] = "mismatch"
        else:
            base["jurisdiction_status"] = "source"
    else:
        base["jurisdiction_status"] = UNKNOWN_PROVENANCE

    publication, publication_bad = _independent_text(item, "publication_date", "published")
    corrupted = corrupted or publication_bad
    if publication:
        base["publication_date"] = publication
        base["publication_date_status"] = "source"
    effective, effective_bad = _independent_text(item, "effective_date")
    corrupted = corrupted or effective_bad
    if effective:
        base["effective_date"] = effective
        base["effective_date_status"] = "source"
    elif publication_filter:
        base["effective_date_status"] = "not_publication_date"

    for field in ("court", "sunset_date", "repealed_date", "effective_end"):
        value, invalid = _independent_text(item, field)
        corrupted = corrupted or invalid
        if value:
            base[field] = value
    # A second normalization pass cannot erase an earlier integrity refusal.
    if item.get("provenance_status") == "corrupted" or item.get("content_hash_mismatch") is True:
        corrupted = True
    if item.get("content_hash_mismatch") is True:
        base["content_hash_mismatch"] = True
    if _is_similarity_authority_hit(item, ""):
        base["similarity_cannot_establish_legal_authority"] = True
        base["authority_label"] = "similarity_not_legal_authority"
    if item.get("provenance") is not None and not isinstance(item.get("provenance"), dict):
        corrupted = True
    base["provenance_status"] = "corrupted" if corrupted else "present"
    if not any((base["uri"], base["citation"], base["source_passage"], base["snippet"], base["cid"])):
        if not corrupted:
            base["provenance_status"] = "missing"
    return base


def _cache_key(family: str, query: str, jurisdiction: str, state: str) -> str:
    return "|".join(
        (
            family,
            str(query or "").strip().lower(),
            str(jurisdiction or "").strip().lower(),
            str(state or "").strip().upper(),
        )
    )


def _normalize_cached_rows(
    rows: Any,
    *,
    family: str,
    retrieval_mode: str,
    requested_jurisdiction: str,
    requested_state: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in rows:
        if len(normalized) >= max_results:
            break
        candidate = normalize_corpus_candidate(
            item,
            source_family=family,
            retrieval_mode=retrieval_mode,
            requested_jurisdiction=requested_jurisdiction,
            requested_state=requested_state,
            retrieved_at=item.get("retrieved_at") if isinstance(item, dict) and isinstance(item.get("retrieved_at"), str) else None,
        )
        normalized.append(candidate)
    return normalized


def _vector_parameters_ready(
    *,
    query_vector: Any,
    collection_name: Optional[str],
    contains_private_facts: bool,
    privacy_policy_accepted: bool,
) -> Optional[str]:
    if not isinstance(query_vector, list) or not query_vector:
        return "query_vector_required"
    if not str(collection_name or "").strip():
        return "collection_name_required"
    if contains_private_facts and not privacy_policy_accepted:
        return "privacy_policy_required"
    return None


def _lookup_local_us_code(
    *,
    query: str,
    index_path: Optional[str],
    titles: Optional[List[str]],
    max_results: int,
    timeout_seconds: float,
) -> Dict[str, Any]:
    from pathlib import Path

    family = CORPUS_FAMILY_US_CODE
    if not index_path:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=RETRIEVAL_MODE_OFFLINE,
            capability="local_us_code_index_missing",
            error_code="local_index_missing",
            error_message="offline US Code lookup requires an explicit local JSONL index path",
            timeout_seconds=timeout_seconds,
        )
    path = Path(index_path).expanduser()
    if not path.is_file():
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=RETRIEVAL_MODE_OFFLINE,
            capability="local_us_code_index_missing",
            error_code="local_index_missing",
            error_message="local US Code index is absent; scrape and setup were not started",
            timeout_seconds=timeout_seconds,
            attempted_backends=["local_us_code_index"],
            extra={"scrape_invoked": False},
        )
    if _search_us_code_async is None:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=RETRIEVAL_MODE_OFFLINE,
            capability="us_code_local_api_unavailable",
            error_code="backend_unavailable",
            error_message="local US Code search API is not importable",
            timeout_seconds=timeout_seconds,
        )

    return _finish_live_call(
        family=family,
        parameters=dict(query=query, titles=list(titles) if titles else None,
                        max_results=max_results, index_path=str(path)),
        timeout_seconds=timeout_seconds,
        backend="local_us_code_index",
        requested_jurisdiction="federal",
        requested_state="",
        max_results=max_results,
        publication_filter=None,
        network_used=False,
        retrieval_mode=RETRIEVAL_MODE_OFFLINE,
    )


def _finish_live_call(
    *,
    family: str,
    parameters: Dict[str, Any],
    timeout_seconds: float,
    backend: str,
    requested_jurisdiction: str,
    requested_state: str,
    max_results: int,
    publication_filter: Optional[Dict[str, str]],
    extra: Optional[Dict[str, Any]] = None,
    network_used: Optional[bool] = None,
    retrieval_mode: str = RETRIEVAL_MODE_LIVE,
) -> Dict[str, Any]:
    outcome, payload = _run_owned_deadline(backend, parameters, timeout_seconds)
    if outcome == "timeout":
        return _bounded_envelope(
            status="timeout",
            family=family,
            retrieval_mode=retrieval_mode,
            capability="deadline_exceeded",
            error_code="timeout",
            error_message="Legal corpus lookup exceeded its owned deadline.",
            timeout_seconds=timeout_seconds,
            attempted_backends=[backend],
            network_used=network_used,
            extra=extra,
        )
    if outcome in {"custody_unavailable", "cleanup_unconfirmed", "invalid_parameters", "cancelled", "output_limit"}:
        return _bounded_envelope(
            status="unavailable",
            family=family,
            retrieval_mode=retrieval_mode,
            capability=outcome,
            error_code=outcome,
            error_message="Legal corpus lookup is unavailable.",
            timeout_seconds=timeout_seconds,
            attempted_backends=[backend],
            extra=extra,
        )
    if outcome == "error":
        return _bounded_envelope(
            status="error",
            family=family,
            retrieval_mode=retrieval_mode,
            capability="backend_error",
            error_code="backend_error",
            error_message="Legal corpus lookup failed.",
            timeout_seconds=timeout_seconds,
            attempted_backends=[backend],
            network_used=network_used,
            extra=extra,
        )
    if not isinstance(payload, dict):
        return _bounded_envelope(
            status="error",
            family=family,
            retrieval_mode=retrieval_mode,
            capability="backend_error",
            error_code="malformed_payload",
            error_message="corpus backend returned a non-dict payload",
            timeout_seconds=timeout_seconds,
            attempted_backends=[backend],
            network_used=network_used,
            extra=extra,
        )
    status = payload.get("status")
    if status == "unavailable":
        return _bounded_envelope(status="unavailable", family=family, retrieval_mode=retrieval_mode,
            capability="backend_unavailable", error_code="backend_unavailable",
            error_message="Legal corpus backend or asset is unavailable.", timeout_seconds=timeout_seconds,
            attempted_backends=[backend], network_used=network_used, extra=extra)
    if type(status) is not str or status not in {"success", "partial_success"} or (status == "success" and payload.get("error")):
        return _bounded_envelope(
            status="error",
            family=family,
            retrieval_mode=retrieval_mode,
            capability="backend_error",
            error_code="backend_error",
            error_message="Legal corpus lookup failed." if payload.get("error") or status == "error" else "",
            timeout_seconds=timeout_seconds,
            attempted_backends=[backend],
            network_used=network_used,
            extra=extra,
        )
    items = _extract_payload_items(payload, "results", "documents", "hits", "data")
    results = [
        normalize_corpus_candidate(
            item,
            source_family=family,
            retrieval_mode=retrieval_mode,
            requested_jurisdiction=requested_jurisdiction,
            requested_state=requested_state,
            publication_filter=publication_filter,
        )
        for item in items[:max_results]
    ]
    return _bounded_envelope(
        status=("partial_success" if status == "partial_success" else "success") if results else "empty",
        family=family,
        retrieval_mode=retrieval_mode,
        capability=backend,
        timeout_seconds=timeout_seconds,
        attempted_backends=[backend],
        results=results,
        network_used=network_used,
        extra=extra,
    )


CANONICAL_CORPUS_PARAMETER_APIS = {
    CORPUS_FAMILY_US_CODE: "search_us_code_corpus_from_parameters",
    CORPUS_FAMILY_STATE_STATUTE: "search_state_law_corpus_from_parameters",
    CORPUS_FAMILY_STATE_ADMIN: "search_state_law_corpus_from_parameters",
    CORPUS_FAMILY_FEDERAL_REGISTER: "search_federal_register_corpus_from_parameters",
    CORPUS_FAMILY_COURT_RULE: "search_court_rules_corpus_from_parameters",
}
_ACQUISITION_BYTE_CAP = 1048576
_OWNED_SOURCE_FIELDS = ("source_text", "locator", "version", "retrieval")


def _acquisition_binding(payload: Any) -> Dict[str, Any]:
    """Accept either a bound acquisition result or its inner request."""
    if not isinstance(payload, Mapping):
        return {"ready": False, "request": None, "execution": {"storage_available": None, "status": "blocked"}}
    if "ready" in payload and "request" in payload:
        execution = payload.get("execution") if isinstance(payload.get("execution"), Mapping) else {}
        return {
            "ready": payload.get("ready") is True and isinstance(payload.get("request"), Mapping),
            "request": payload.get("request") if isinstance(payload.get("request"), Mapping) else None,
            "execution": dict(execution),
            "questions": list(payload.get("questions") or []),
        }
    program = payload.get("program") if isinstance(payload.get("program"), Mapping) else {}
    ready = bool(payload.get("jurisdiction") and payload.get("law_query_date") and program.get("query_text"))
    return {"ready": ready, "request": dict(payload) if ready else None, "execution": {}, "questions": []}


def _selected_corpus_families(request: Mapping[str, Any]) -> List[tuple]:
    plan = request.get("corpus_plan") if isinstance(request.get("corpus_plan"), Mapping) else {}
    families = {
        str(family or "").strip()
        for family in (plan.get("authority_families") or [])
        if str(family or "").strip()
    }
    selected = [
        (CORPUS_FAMILY_US_CODE, bool(plan.get("search_us_code"))),
        (CORPUS_FAMILY_STATE_STATUTE, bool(plan.get("search_state_laws"))),
        (CORPUS_FAMILY_FEDERAL_REGISTER, bool(plan.get("search_federal_register"))),
        (CORPUS_FAMILY_STATE_ADMIN, bool(plan.get("search_state_administrative_rules"))),
        (CORPUS_FAMILY_COURT_RULE, _plan_searches_court_rules(dict(plan), families)),
    ]
    return [(family, CANONICAL_CORPUS_PARAMETER_APIS[family]) for family, enabled in selected if enabled]


def _parameter_record(request: Mapping[str, Any], family: str, api_name: str, *, max_results: int, timeout_seconds: float, max_bytes: int) -> Dict[str, Any]:
    plan = request.get("corpus_plan") if isinstance(request.get("corpus_plan"), Mapping) else {}
    program = request.get("program") if isinstance(request.get("program"), Mapping) else {}
    state_code = str(plan.get("state_code") or "")
    jurisdiction = str(request.get("jurisdiction") or plan.get("jurisdiction") or "")
    parameters: Dict[str, Any] = {
        "collection_name": "local-private-legal-fixture" if program.get("retrieval_mode") != RETRIEVAL_MODE_LIVE else str(program.get("collection_name") or ""),
        "query_text": str(program.get("query_text") or ""),
        "top_k": max_results,
        "auto_setup_venv": False,
        "chunk_lookup_enabled": False,
        "download_corpus": False,
        "initialize_common_crawl": False,
        "law_query_date": request.get("law_query_date"),
        "timeout_seconds": timeout_seconds,
        "max_bytes": max_bytes,
        "source_family": family,
    }
    if family in {CORPUS_FAMILY_STATE_STATUTE, CORPUS_FAMILY_STATE_ADMIN} or (family == CORPUS_FAMILY_COURT_RULE and state_code):
        parameters["state"] = state_code
    if family == CORPUS_FAMILY_COURT_RULE:
        parameters["jurisdiction"] = "federal" if jurisdiction == "federal" else "state"
    elif jurisdiction:
        parameters["jurisdiction"] = jurisdiction
    return {
        "parameter_api": api_name,
        "parameters": parameters,
        "allowed_backend": api_name,
    }


def _local_cache_from_rows(request: Mapping[str, Any], local_rows: Optional[Mapping[str, Any]], offline_cache: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cache: Dict[str, Any] = dict(offline_cache or {})
    if not isinstance(local_rows, Mapping):
        return cache
    program = request.get("program") if isinstance(request.get("program"), Mapping) else {}
    plan = request.get("corpus_plan") if isinstance(request.get("corpus_plan"), Mapping) else {}
    query = str(program.get("query_text") or "")
    jurisdiction = str(request.get("jurisdiction") or "")
    state_code = str(plan.get("state_code") or "")
    resolved = resolve_explicit_jurisdiction(jurisdiction)
    jurisdiction_key = "" if resolved == UNKNOWN_LEGAL_CONTEXT else resolved
    for family, rows in local_rows.items():
        family_name = str(family or "")
        if family_name not in CANONICAL_CORPUS_PARAMETER_APIS or not isinstance(rows, list):
            continue
        cache[_cache_key(family_name, query, jurisdiction_key, state_code)] = list(rows)
    return cache


def _owned_source_candidate(row: Mapping[str, Any], *, law_query_date: Any, max_bytes: int) -> tuple:
    """Keep a row only when owned text, locator, version, and retrieval are present.

    A snippet, score, or caller applicability flag is not a candidate and is not proof.
    """
    passage = row.get("source_passage") if isinstance(row.get("source_passage"), str) else ""
    passage_status = str(row.get("passage_status") or "")
    locator = ""
    locator_kind = ""
    if row.get("uri_status") == "source" and isinstance(row.get("uri"), str) and row.get("uri"):
        locator = row["uri"]
        locator_kind = "uri"
    elif row.get("citation_status") == "source" and isinstance(row.get("citation"), str) and row.get("citation"):
        locator = row["citation"]
        locator_kind = "citation"
    version = row.get("corpus_version") if isinstance(row.get("corpus_version"), str) else ""
    if passage_status != "full_text" or not passage:
        reason = "snippet_not_owned" if row.get("snippet") or passage_status == "snippet_only" else "source_text_missing"
        return None, reason
    if not locator:
        return None, "locator_missing"
    if not version.strip():
        return None, "missing_edition"
    encoded = passage.encode("utf-8")
    if len(encoded) > max_bytes:
        return None, "byte_bound_exceeded"
    retrieval = {
        "retrieved_at": row.get("retrieved_at"),
        "retrieval_mode": row.get("retrieval_mode"),
        "source_family": row.get("source_family"),
        "content_hash": row.get("content_hash"),
        "content_hash_scope": row.get("content_hash_scope"),
        "provenance_status": row.get("provenance_status"),
        "corpus_id": row.get("corpus_id"),
        "jurisdiction_status": row.get("jurisdiction_status"),
        "effective_date": row.get("effective_date"),
        "effective_date_status": row.get("effective_date_status"),
    }
    candidate = {
        "source_text": passage,
        "source_byte_length": len(encoded),
        "locator": locator,
        "locator_kind": locator_kind,
        "version": version.strip(),
        "retrieval": retrieval,
        "applicability": UNKNOWN_LEGAL_CONTEXT,
        "applicable": False,
        "verified": False,
        "support_eligible": False,
        "proof": False,
        "relevance_is_not_proof": True,
        "law_query_date": law_query_date,
        "edition_selected": False,
    }
    return candidate, "candidate"


def _operation_status(envelope_status: str, reasons: List[str], owned: List[Dict[str, Any]]) -> str:
    if owned:
        return "candidates"
    if "missing_edition" in reasons and envelope_status in {"success", "partial_success", "empty", "candidates"}:
        return "missing_edition"
    if "byte_bound_exceeded" in reasons:
        return "unavailable"
    if envelope_status == "timeout":
        return "timeout"
    if envelope_status in {"unavailable", "error"}:
        return envelope_status
    if envelope_status in {"success", "partial_success"} and not owned:
        if reasons and all(reason in {"snippet_not_owned", "source_text_missing", "locator_missing"} for reason in reasons):
            return "incomplete"
        return "empty"
    return envelope_status or "empty"


def _resume_for(operations: List[Dict[str, Any]], *, blocked: str = "") -> Dict[str, Any]:
    reasons = [str(item.get("status") or "") for item in operations]
    if blocked == "cancelled":
        return {"resumable": False, "next_action": "awaiting_user", "worker_stalled": False, "completed_operations": [], "pending_statuses": ["cancelled"]}
    if blocked == "blocked":
        return {"resumable": True, "next_action": "resolve_legal_context", "worker_stalled": False, "completed_operations": [], "pending_statuses": ["blocked"]}
    pending = [item for item in operations if item.get("status") in {"unavailable", "timeout", "missing_edition", "error", "incomplete", "refused"}]
    completed = [str(item.get("source_family") or "") for item in operations if item.get("status") in {"candidates", "empty"}]
    if any(item.get("status") == "timeout" for item in operations):
        action = "retry_timeout"
    elif any(item.get("status") == "missing_edition" for item in operations):
        action = "supply_edition"
    elif any(item.get("status") in {"unavailable", "error"} for item in operations):
        action = "retry_unavailable"
    elif any(item.get("status") == "incomplete" for item in operations):
        action = "supply_owned_source_text"
    elif any(item.get("status") == "refused" for item in operations):
        action = "resolve_purpose_gate"
    else:
        action = "none"
    return {
        "resumable": bool(pending) or action != "none",
        "next_action": action,
        "worker_stalled": False,
        "completed_operations": completed,
        "pending_statuses": [str(item.get("status") or "") for item in pending] or reasons,
    }


def _roll_up_status(operations: List[Dict[str, Any]]) -> str:
    statuses = [str(item.get("status") or "") for item in operations]
    if any(status == "candidates" for status in statuses):
        return "candidates"
    for status in ("timeout", "unavailable", "error", "missing_edition", "incomplete", "refused", "empty"):
        if status in statuses:
            return status
    return "empty"


def acquire_bounded_canonical_legal_sources(
    binding: Any,
    *,
    owner_id: str,
    case_id: str,
    purpose: str = "public_law_citation",
    data_class: str = "public_legal_source_graph",
    provider_kind: str = "legal_corpus",
    policy_reader: Optional[Any] = None,
    provider_loader: Optional[Any] = None,
    allowed_backends: Optional[Iterable[str]] = None,
    deadline_seconds: Optional[float] = None,
    max_results: Optional[int] = None,
    max_bytes: int = 65536,
    retrieval_mode: Optional[str] = None,
    offline_cache: Optional[Dict[str, Any]] = None,
    local_rows: Optional[Mapping[str, Any]] = None,
    index_path: Optional[str] = None,
    query_vector: Optional[List[float]] = None,
    collection_name: Optional[str] = None,
    privacy_policy_accepted: bool = False,
    contains_private_facts: bool = False,
    cancelled: bool = False,
) -> Dict[str, Any]:
    """Acquire owned legal-source candidates for one explicit acquisition request.

    Local cache and index reads do not infer embeddings and do not download a
    corpus. A live parameter-API call is dispatched only after the purpose and
    data-class gate allows it. Search hits are not applicability or proof.
    """
    unpacked = _acquisition_binding(binding)
    request = unpacked.get("request") if isinstance(unpacked.get("request"), Mapping) else None
    execution = unpacked.get("execution") if isinstance(unpacked.get("execution"), Mapping) else {}
    base = {
        "owner_id": str(owner_id or ""),
        "case_id": str(case_id or ""),
        "purpose": purpose if type(purpose) is str else "",
        "data_class": data_class if type(data_class) is str else "",
        "candidates": [],
        "operations": [],
        "model_inference_used": False,
        "commoncrawl_initialized": False,
        "corpus_download_started": False,
        "backend_invoked": False,
        "remote_dispatched": False,
        "applicability": UNKNOWN_LEGAL_CONTEXT,
        "proof": False,
        "contains_private_narrative": False,
        "live_model_identity_verified": False,
    }
    if cancelled:
        base.update(status="cancelled", error_code="cancelled", gate={"status": "not_required", "code": "cancelled"}, resume=_resume_for([], blocked="cancelled"))
        return base
    if execution.get("storage_available") is False or execution.get("status") == "unavailable":
        base.update(status="unavailable", error_code="storage_unavailable", gate={"status": "not_required", "code": "storage_unavailable"},
            resume=_resume_for([{"status": "unavailable", "source_family": ""}], blocked=""))
        return base
    if not unpacked.get("ready") or request is None:
        base.update(status="blocked", error_code="legal_context_not_ready", gate={"status": "not_required", "code": "legal_context_not_ready"},
            questions=list(unpacked.get("questions") or []), resume=_resume_for([], blocked="blocked"))
        return base

    try:
        bounded_results = int(request.get("bounds", {}).get("max_results", 5) if max_results is None else max_results)
    except (TypeError, ValueError):
        bounded_results = 0
    if type(bounded_results) is not int or isinstance(bounded_results, bool) or not 1 <= bounded_results <= _BOUNDED_RESULT_CAP:
        base.update(status="unavailable", error_code="invalid_result_limit", gate={"status": "not_required", "code": "invalid_result_limit"},
            resume=_resume_for([{"status": "unavailable", "source_family": ""}]))
        return base
    try:
        timeout_value = float(request.get("bounds", {}).get("timeout_seconds", 5.0) if deadline_seconds is None else deadline_seconds)
    except (TypeError, ValueError):
        timeout_value = 0.0
    if not math.isfinite(timeout_value) or timeout_value <= 0 or timeout_value > _BOUNDED_TIMEOUT_CAP_SECONDS:
        base.update(status="unavailable", error_code="invalid_timeout", gate={"status": "not_required", "code": "invalid_timeout"},
            resume=_resume_for([{"status": "unavailable", "source_family": ""}]))
        return base
    if type(max_bytes) is not int or isinstance(max_bytes, bool) or not 1 <= max_bytes <= _ACQUISITION_BYTE_CAP:
        base.update(status="unavailable", error_code="invalid_byte_bound", gate={"status": "not_required", "code": "invalid_byte_bound"},
            resume=_resume_for([{"status": "unavailable", "source_family": ""}]))
        return base

    mode = str(retrieval_mode or (request.get("program") or {}).get("retrieval_mode") or RETRIEVAL_MODE_OFFLINE).strip().lower()
    if mode not in BOUNDED_RETRIEVAL_MODES:
        base.update(status="unavailable", error_code="retrieval_mode_required", gate={"status": "not_required", "code": "retrieval_mode_required"},
            resume=_resume_for([{"status": "unavailable", "source_family": ""}]))
        return base
    allowed = {str(item) for item in allowed_backends} if allowed_backends is not None else set(CANONICAL_CORPUS_PARAMETER_APIS.values())
    families = _selected_corpus_families(request)
    gate: Dict[str, Any] = {"status": "not_required", "code": "local_first", "policy_read": False, "provider_loader_called": False}
    if mode == RETRIEVAL_MODE_LIVE:
        from mediator.hook_runtime import prepare_remote_hook_query

        if policy_reader is None:
            gate = {"status": "refused", "code": "consent_missing", "policy_read": False, "provider_loader_called": False}
        else:
            gate = prepare_remote_hook_query(
                policy_reader=policy_reader,
                provider_loader=provider_loader,
                owner_id=str(owner_id or ""),
                case_id=str(case_id or ""),
                purpose=purpose,
                provider_kind=provider_kind,
                data_class=data_class,
                tools=False,
                citation=str((request.get("program") or {}).get("query_text") or ""),
                complaint_text=None,
            )
        if gate.get("status") != "available" or gate.get("effectful") is not True:
            refused = "unavailable" if gate.get("status") == "unavailable" else "refused"
            base.update(status=refused, error_code=str(gate.get("code") or "consent_missing"), gate={
                "status": gate.get("status"), "code": gate.get("code"), "policy_read": gate.get("policy_read"),
                "provider_loader_called": gate.get("provider_loader_called"),
            }, remote_dispatched=False, resume=_resume_for([{"status": refused, "source_family": ""}]))
            return base
    elif query_vector:
        base.update(status="unavailable", error_code="local_inference_refused", gate=gate,
            resume=_resume_for([{"status": "unavailable", "source_family": ""}]))
        return base

    explicit_local = local_rows is not None or isinstance(offline_cache, dict) or bool(index_path)
    if mode != RETRIEVAL_MODE_LIVE and not explicit_local:
        base.update(status="unavailable", error_code="offline_asset_missing", gate=gate, remote_dispatched=False,
            resume=_resume_for([{"status": "unavailable", "source_family": ""}]))
        return base
    cache = _local_cache_from_rows(request, local_rows, offline_cache if isinstance(offline_cache, dict) else None)
    law_query_date = request.get("law_query_date")
    plan = request.get("corpus_plan") if isinstance(request.get("corpus_plan"), Mapping) else {}
    query = str((request.get("program") or {}).get("query_text") or "")
    operations: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    for family, api_name in families:
        record = _parameter_record(request, family, api_name, max_results=bounded_results, timeout_seconds=timeout_value, max_bytes=max_bytes)
        operation: Dict[str, Any] = {
            "source_family": family,
            "parameter_api": api_name,
            "parameters": record["parameters"],
            "backend_allowed": api_name in allowed,
            "backend_invoked": False,
            "model_inference_used": False,
            "commoncrawl_initialized": False,
            "corpus_download_started": False,
            "deadline_seconds": timeout_value,
            "max_results": bounded_results,
            "max_bytes": max_bytes,
            "withheld": [],
            "candidate_count": 0,
        }
        if api_name not in allowed:
            operation.update(status="unavailable", error_code="backend_not_allowed")
            operations.append(operation)
            continue
        lookup_mode = RETRIEVAL_MODE_CACHE if mode != RETRIEVAL_MODE_LIVE else RETRIEVAL_MODE_LIVE
        if mode == RETRIEVAL_MODE_OFFLINE and index_path and family == CORPUS_FAMILY_US_CODE and not local_rows:
            lookup_mode = RETRIEVAL_MODE_OFFLINE
        try:
            envelope = lookup_bounded_legal_corpus(
                source_family=family,
                query=query,
                retrieval_mode=lookup_mode,
                jurisdiction=str(request.get("jurisdiction") or ""),
                state=str(plan.get("state_code") or "") or None,
                court_jurisdiction=record["parameters"].get("jurisdiction") if family == CORPUS_FAMILY_COURT_RULE else None,
                max_results=bounded_results,
                timeout_seconds=timeout_value,
                offline_cache=cache if lookup_mode != RETRIEVAL_MODE_LIVE else None,
                index_path=index_path if lookup_mode == RETRIEVAL_MODE_OFFLINE else None,
                collection_name=collection_name,
                query_vector=query_vector if lookup_mode == RETRIEVAL_MODE_LIVE else None,
                contains_private_facts=contains_private_facts if lookup_mode == RETRIEVAL_MODE_LIVE else False,
                privacy_policy_accepted=privacy_policy_accepted if lookup_mode == RETRIEVAL_MODE_LIVE else False,
                live_backend="corpus",
            )
        except Exception:
            envelope = {"status": "unavailable", "error_code": "backend_unavailable", "results": []}
        operation["backend_invoked"] = True
        base["backend_invoked"] = True
        if lookup_mode == RETRIEVAL_MODE_LIVE:
            base["remote_dispatched"] = True
            operation["model_inference_used"] = False
        reasons: List[str] = []
        owned: List[Dict[str, Any]] = []
        for row in envelope.get("results") or []:
            if not isinstance(row, Mapping):
                reasons.append("source_text_missing")
                operation["withheld"].append({"reason": "source_text_missing"})
                continue
            candidate, reason = _owned_source_candidate(row, law_query_date=law_query_date, max_bytes=max_bytes)
            if candidate is None:
                reasons.append(reason)
                operation["withheld"].append({"reason": reason, "passage_status": row.get("passage_status"), "provenance_status": row.get("provenance_status")})
                continue
            candidate["parameter_api"] = api_name
            candidate["source_family"] = family
            owned.append(candidate)
        status = _operation_status(str(envelope.get("status") or ""), reasons, owned)
        if status == "unavailable" and "byte_bound_exceeded" in reasons and not owned:
            error_code = "byte_bound_exceeded"
        else:
            error_code = str(envelope.get("error_code") or "")
        if status == "missing_edition":
            error_code = "missing_edition"
        operation.update(status=status, error_code=error_code, envelope_status=str(envelope.get("status") or ""), candidate_count=len(owned))
        candidates.extend(owned[:bounded_results])
        operations.append(operation)
        if len(candidates) >= bounded_results:
            candidates = candidates[:bounded_results]
            break
    if not families:
        base.update(status="empty", error_code="", operations=[], candidates=[], gate=gate, resume=_resume_for([{"status": "empty", "source_family": ""}]))
        return base
    base["model_inference_used"] = any(bool(item.get("model_inference_used")) for item in operations)
    base.update(
        status=_roll_up_status(operations),
        error_code=next((str(item.get("error_code") or "") for item in operations if item.get("status") == _roll_up_status(operations) and item.get("error_code")), ""),
        candidates=candidates,
        operations=operations,
        gate={"status": gate.get("status"), "code": gate.get("code"), "policy_read": bool(gate.get("policy_read")), "provider_loader_called": bool(gate.get("provider_loader_called"))},
        resume=_resume_for(operations),
        result_count=len(candidates),
        bounds={"max_results": bounded_results, "timeout_seconds": timeout_value, "max_bytes": max_bytes},
    )
    return base


_TREATMENT_LAYER_KEYS = ("authority_treatment_edges", "treatment_records", "treatment_summary")
_TREATMENT_TYPE_ALIASES = ("relation_type", "treatment_type", "type", "treatment", "effect", "disposition")
_ADVERSE_TREATMENT_LABELS = frozenset({
    "adverse", "superseded", "superseding", "repealed", "repealing", "repeal",
})
_TREATMENT_CANONICAL = {
    "superseding": "superseded",
    "repealing": "repealed",
    "repeal": "repealed",
}
_OPEN_INTERVAL_END = "9999-12-31"


def _iso_law_day(value: Any) -> str:
    """Accept a calendar day. A retrieval timestamp is not an applicable-law day."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) != 10 or "T" in text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _mapping_layers(record: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    layers = [record]
    for key in ("metadata", "provenance", "retrieval"):
        nested = record.get(key)
        if isinstance(nested, Mapping):
            layers.append(nested)
    return layers


def retain_acquired_treatment_records(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Keep canonical and metadata treatment rows.

    An empty list or an empty type alias does not erase an adverse,
    superseding, or repealing row stored on another layer.
    """
    if not isinstance(record, Mapping):
        return []
    retained: List[Dict[str, Any]] = []
    seen = set()
    for container in _mapping_layers(record):
        for key in _TREATMENT_LAYER_KEYS:
            rows = container.get(key)
            if key == "treatment_summary" and isinstance(rows, Mapping):
                rows = rows.get("records")
            if not rows:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                labels = []
                for alias in _TREATMENT_TYPE_ALIASES:
                    value = row.get(alias)
                    if isinstance(value, str) and value.strip():
                        label = value.strip()
                        if label not in labels:
                            labels.append(label)
                if not labels:
                    continue
                for label in labels:
                    canonical = _TREATMENT_CANONICAL.get(label.lower(), label)
                    signature = (
                        canonical.lower(),
                        str(row.get("source_authority_id") or row.get("treated_by_authority_id") or ""),
                        str(row.get("target_authority_id") or row.get("treated_authority_id") or row.get("target_id") or ""),
                        str(row.get("treatment_id") or row.get("edge_id") or ""),
                        str(row.get("explanation") or row.get("treatment_explanation") or ""),
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    kept = {key: value for key, value in row.items() if key not in _TREATMENT_TYPE_ALIASES or row.get(key) not in ("", None)}
                    kept["treatment_type"] = label
                    kept["relation_type"] = canonical
                    kept["layer_retained"] = True
                    if label.lower() in _ADVERSE_TREATMENT_LABELS or canonical.lower() in _ADVERSE_TREATMENT_LABELS:
                        kept["adverse_treatment_retained"] = True
                    retained.append(kept)
    return retained


def _explicit_applicable_law_day(legal_context: Any) -> str:
    if not isinstance(legal_context, Mapping):
        return ""
    dated = legal_context.get("applicable_law_date")
    if isinstance(dated, Mapping):
        if dated.get("role") not in (None, "", DATE_ROLE_APPLICABLE_LAW):
            return ""
        if dated.get("is_uncertain"):
            return ""
        return _iso_law_day(str(dated.get("precise_date") or ""))
    return _iso_law_day(dated if isinstance(dated, str) else "")


def _candidate_authority_id(candidate: Mapping[str, Any]) -> str:
    for container in _mapping_layers(candidate):
        for key in ("authority_id", "authority_identity", "id"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    locator = candidate.get("locator")
    return locator.strip() if isinstance(locator, str) else ""


def _candidate_version_rows(candidate: Mapping[str, Any]) -> List[Dict[str, Any]]:
    version = candidate.get("version") if isinstance(candidate.get("version"), str) else ""
    version = version.strip()
    authority_id = _candidate_authority_id(candidate)
    retrieval = candidate.get("retrieval") if isinstance(candidate.get("retrieval"), Mapping) else {}
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), Mapping) else {}
    effective = ""
    for container in (candidate, retrieval, metadata):
        day = _iso_law_day(container.get("effective_date"))
        if day:
            effective = day
            break
    ends = []
    for key in ("sunset_date", "repeal_date", "superseded_date", "expiration_date"):
        for container in (candidate, retrieval, metadata):
            day = _iso_law_day(container.get(key))
            if day:
                ends.append(day)
    primary = {
        "authority_id": authority_id,
        "version": version,
        "law_version_id": str(candidate.get("law_version_id") or metadata.get("law_version_id") or (f"{authority_id}:{version}" if authority_id and version else "")),
        "effective_date": effective,
        "end_date": min(ends) if ends else "",
        "source_text": candidate.get("source_text") if isinstance(candidate.get("source_text"), str) else "",
        "citation": str(candidate.get("citation") or metadata.get("citation") or candidate.get("locator") or ""),
        "retrieved_at": retrieval.get("retrieved_at"),
    }
    rows = [primary]
    supplied = candidate.get("law_versions")
    if not isinstance(supplied, list):
        supplied = metadata.get("law_versions")
    if isinstance(supplied, list):
        for item in supplied:
            if not isinstance(item, Mapping):
                continue
            item_version = str(item.get("version") or item.get("authority_version") or "").strip()
            item_id = str(item.get("authority_id") or authority_id).strip()
            if item_version == version and item_id == authority_id:
                continue
            item_ends = [_iso_law_day(item.get(key)) for key in ("sunset_date", "repeal_date", "superseded_date", "expiration_date")]
            item_ends = [day for day in item_ends if day]
            rows.append({
                "authority_id": item_id or authority_id,
                "version": item_version,
                "law_version_id": str(item.get("law_version_id") or (f"{item_id or authority_id}:{item_version}" if item_version else "")),
                "effective_date": _iso_law_day(item.get("effective_date")),
                "end_date": min(item_ends) if item_ends else "",
                "source_text": primary["source_text"] if item_version == version else "",
                "citation": str(item.get("citation") or primary["citation"] or ""),
                "retrieved_at": primary["retrieved_at"],
                "embedded_other_version": True,
            })
    return rows


def _interval_contains(row: Mapping[str, Any], day: str) -> bool:
    start = str(row.get("effective_date") or "")
    end = str(row.get("end_date") or "")
    if not start or not day or start > day:
        return False
    return not end or day < end


def _intervals_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if not left.get("effective_date") or not right.get("effective_date"):
        return False
    left_end = str(left.get("end_date") or _OPEN_INTERVAL_END)
    right_end = str(right.get("end_date") or _OPEN_INTERVAL_END)
    return str(left.get("effective_date")) < right_end and str(right.get("effective_date")) < left_end


def _version_known(version: str) -> bool:
    return version.strip().lower() not in {"", "unknown", "unspecified", "n/a", "na", "none", "null", "current", "latest", "unverified"}


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
        "court_rules": [],
    }

    diagnostics = {}
    selected = [
        ("statutes", CORPUS_FAMILY_US_CODE, plan["search_us_code"]),
        ("state_statutes", CORPUS_FAMILY_STATE_STATUTE, plan["search_state_laws"]),
        ("regulations", CORPUS_FAMILY_FEDERAL_REGISTER, plan["search_federal_register"]),
        ("administrative_rules", CORPUS_FAMILY_STATE_ADMIN, plan["search_state_administrative_rules"]),
        ("court_rules", CORPUS_FAMILY_COURT_RULE, _plan_searches_court_rules(plan, families)),
    ]
    for bucket, family, enabled in selected:
        if not enabled:
            continue
        envelope = lookup_bounded_legal_corpus(
            source_family=family, query=query,
            retrieval_mode=program.get("retrieval_mode", RETRIEVAL_MODE_OFFLINE),
            jurisdiction=jurisdiction, state=state_code or None,
            court_jurisdiction=program.get("court_jurisdiction") or ("federal" if jurisdiction == "federal" else "state"),
            max_results=max_results, timeout_seconds=program.get("timeout_seconds", 5.0),
            collection_name=program.get("collection_name"), query_vector=program.get("query_vector"),
            index_path=program.get("index_path"), offline_cache=program.get("offline_cache"),
            start_date=program.get("start_date"), end_date=program.get("end_date"),
            contains_private_facts=program.get("contains_private_facts", True),
            privacy_policy_accepted=program.get("privacy_policy_accepted", False))
        results[bucket] = list(envelope.get("results") or [])
        diagnostics[bucket] = {key: envelope.get(key) for key in
            ("status", "capability", "error_code", "retrieval_mode", "applicability")}
    # Explicit case/docket discovery retains its separate, established route.
    if plan["search_case_law"] and ("case_law" in families or not families):
        results["case_law"] = search_recap_documents(query, max_results=max_results)
    if plan["search_case_law"] and ("docket_material" in families or not families):
        results["docket_materials"] = search_recap_documents(query, max_results=max_results)
    court_rules_diagnostics = diagnostics.get("court_rules")

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
            "court_rules_diagnostics": court_rules_diagnostics,
            "corpus_diagnostics": diagnostics,
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
    "SourcedLegalRequirement",
    "adapt_sourced_legal_requirements",
    "intake_legal_selection",
    "build_bounded_legal_acquisition_request",
    "acquire_bounded_canonical_legal_sources",
    "CANONICAL_CORPUS_PARAMETER_APIS",
    "unresolved_legal_requirement",
    "legal_requirement_search_plan",
    "lookup_bounded_legal_corpus",
    "normalize_corpus_candidate",
    "BOUNDED_CORPUS_FAMILIES",
    "RETRIEVAL_MODE_CACHE",
    "RETRIEVAL_MODE_OFFLINE",
    "RETRIEVAL_MODE_LIVE",
]

from .legal_corpus import lookup_bounded_legal_corpus, build_bounded_legal_acquisition_request, constrain_assertions_to_corpus, handoff_acquired_legal_sources
