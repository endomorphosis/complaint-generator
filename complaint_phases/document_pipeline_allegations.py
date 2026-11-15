"""Allegation assembly delegated from FormalComplaintDocumentBuilder."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from complaint_phases.document_pipeline import (
    _coerce_list,
    _contains_date_anchor,
    _contains_hearing_timing_marker,
    _contains_response_date_marker,
    _contains_sequence_timing_marker,
    _contains_staff_identity_marker,
    _extract_dated_event_clause,
    _join_chronology_segments,
    _normalize_identifier_list,
    _unique_preserving_order,
)

def _formalize_allegation_fragment(self, value: Any) -> str:
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

def _is_factual_allegation_candidate(self, value: Any) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return False
    lowered = text.lower()
    if re.match(r"^(as to [^,]+, )?plaintiff (seeks|requests|asks|demands)\b", lowered):
        return False
    if lowered.startswith(("requested relief", "relief requested", "element supported:")):
        return False
    if lowered.startswith(("evidence shows facts supporting", "the intake record describes facts supporting")):
        return False
    if "the strongest supporting material is" in lowered:
        return False
    if re.match(r"^(as to [^,]+, )?(title\s+[ivxlcdm0-9]+\b|\d+\s+u\.s\.c\.|\d+\s+c\.f\.r\.|[a-z]{2,6}\.\s+gov\.\s+code\b)", lowered):
        return False
    if len(text) > 360:
        return False
    if not re.search(
        r"\b(was|were|is|are|reported|complained|terminated|fired|retaliated|denied|refused|told|informed|notified|requested|sought|seek|experienced|suffered|lost|made|engaged|opposed|filed|submitted|sent|issued|signed|emailed|wrote|received|occurred|happened|subjected|demoted|suspended|disciplined|reduced|exchanged|used|included|includes|requires|required|must|states|describes|shows|reflects|discusses|provides)\b",
        lowered,
    ):
        return False
    return True

def _synthesize_narrative_allegations(self, allegations: List[str]) -> List[str]:
    cleaned = [str(item).strip() for item in allegations if str(item).strip()]
    if not cleaned:
        return []

    def _normalize_adverse_clause(clause: str) -> str:
        text = str(clause or "").strip().rstrip(".!?")
        if re.match(r"^(after|following)\b", text, flags=re.IGNORECASE) and "," in text:
            text = text.split(",", 1)[1].strip()
        return text

    def _normalize_harm_clause(clause: str) -> str:
        text = str(clause or "").strip().rstrip(".!?")
        text = re.sub(r",?\s+as a result$", "", text, flags=re.IGNORECASE)
        text = re.sub(r",?\s+as a direct result$", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _pick(pattern: str, *, require_plaintiff: bool = False) -> str:
        for item in cleaned:
            lowered = item.lower()
            if require_plaintiff and "plaintiff" not in lowered:
                continue
            if re.search(pattern, lowered):
                return item.rstrip(".!?")
        return ""

    report_clause = _pick(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", require_plaintiff=True)
    adverse_clause = _pick(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b")
    harm_clause = _pick(r"\blost (pay|wages|salary|income|benefits)\b|\b(suffered|experienced)\b", require_plaintiff=True)
    harm_already_tied_to_adverse_action = any(
        re.search(r"\b(lost|suffered|experienced)\b", item.lower())
        and re.search(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied)\b", item.lower())
        for item in cleaned
    )

    synthesized: List[str] = []
    if report_clause and adverse_clause:
        synthesized.append(f"After {report_clause}, {_normalize_adverse_clause(adverse_clause)}.")
    if harm_clause and not harm_already_tied_to_adverse_action:
        normalized_harm_clause = _normalize_harm_clause(harm_clause)
        loss_match = re.search(r"\blost ([^.]+)", normalized_harm_clause, flags=re.IGNORECASE)
        if loss_match:
            synthesized.append(f"As a direct result of Defendant's conduct, Plaintiff lost {loss_match.group(1).strip()}." )
    return _unique_preserving_order(synthesized)

def _prune_near_duplicate_allegations(self, allegations: List[str]) -> List[str]:
    def _tokens(value: str) -> set[str]:
        scrubbed = re.sub(r"\(see exhibit [^)]+\)", "", value, flags=re.IGNORECASE)
        return {
            token
            for token in re.split(r"\W+", scrubbed.lower())
            if len(token) >= 4 and token not in {"plaintiff", "defendant", "exhibit", "after", "those", "this", "that"}
        }

    def _categories(value: str) -> set[str]:
        lowered = value.lower()
        flags = set()
        if re.search(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", lowered):
            flags.add("report")
        if re.search(r"\b(terminated|fired|demoted|suspended|disciplined|retaliated|denied|removed|stripped)\b", lowered) or re.search(r"\b(end(?:ed|ing))\b[^.]{0,40}\bemployment\b", lowered):
            flags.add("adverse")
        if re.search(r"\b(lost|suffered|experienced|benefits|wages|salary|income|opportunities)\b", lowered):
            flags.add("harm")
        if re.search(r"\b(notice|informal review|review protections?|hearing|grievance|appeal|due process)\b", lowered):
            flags.add("policy_process")
        return flags

    def _features(value: str) -> set[str]:
        lowered = value.lower()
        flags = set()
        if re.search(r"\b(reported|complained|opposed|informed|notified|told|requested)\b", lowered):
            flags.add("report")
        if re.search(r"\b(human resources|hr)\b", lowered):
            flags.add("hr")
        if re.search(r"\bregional management|management\b", lowered):
            flags.add("management")
        if re.search(r"\b(key|major)\s+accounts?\b|\b(accounts?)\b[^.]{0,20}\b(removed|stripped|taken away)\b|\b(removed|stripped|took away)\b[^.]{0,20}\baccounts?\b", lowered):
            flags.add("accounts")
        if re.search(r"\bovertime\b", lowered):
            flags.add("overtime")
        if re.search(r"\bshift(s)?\b", lowered):
            flags.add("shifts")
        if re.search(r"\b(absences?|attendance|treatment-related absences?)\b", lowered):
            flags.add("absences")
        if re.search(r"\b(disciplined|discipline|wrote me up|write-up|write up)\b", lowered):
            flags.add("discipline")
        if re.search(r"\b(accommodation|accommodate|light duty|schedule flexibility|medical restrictions?|doctor-imposed restrictions?)\b", lowered):
            flags.add("accommodation")
        if re.search(r"\b(restrictions?|light duty|schedule flexibility)\b", lowered):
            flags.add("restrictions")
        if re.search(r"\b(terminated|fired)\b", lowered) or re.search(r"\b(end(?:ed|ing))\b[^.]{0,40}\bemployment\b", lowered):
            flags.add("termination")
        if re.search(r"\b(wages|pay|salary|income|benefits)\b", lowered):
            flags.add("economic_harm")
        if re.search(r"\b(career opportunities|future opportunities|opportunities)\b", lowered):
            flags.add("opportunities")
        if re.search(r"\bnotice to the applicant\b|\bwritten notice\b", lowered):
            flags.add("notice")
        if re.search(r"\binformal review\b|\breview protections?\b|\bhearing\b|\bgrievance\b|\bappeal\b", lowered):
            flags.add("review_process")
        if re.search(r"\b(denial notice|denied assistance|denying assistance|loss of assistance|terminated assistance|termination)\b", lowered):
            flags.add("denial_action")
        if re.search(r"\bwithout providing\b|\bfailed to provide\b|\bshould have accompanied\b", lowered):
            flags.add("process_violation")
        return flags

    kept: List[str] = []
    for candidate in allegations:
        candidate_tokens = _tokens(candidate)
        candidate_categories = _categories(candidate)
        candidate_features = _features(candidate)
        candidate_is_chronology = candidate.lower().startswith("the chronology shows that ")
        skip = False
        for index, existing in enumerate(kept):
            existing_tokens = _tokens(existing)
            existing_categories = _categories(existing)
            existing_features = _features(existing)
            existing_is_chronology = existing.lower().startswith("the chronology shows that ")
            if not candidate_tokens or not existing_tokens:
                continue
            if candidate_is_chronology and not existing_is_chronology:
                continue
            if existing_is_chronology and not candidate_is_chronology:
                continue
            if (
                "without the notice and review protections described in the governing process" in candidate.lower()
                and "without the notice and review protections described in the governing process" not in existing.lower()
                and "denial notice" in candidate.lower()
                and "denial notice" in existing.lower()
                and _contains_date_anchor(candidate)
                and _contains_date_anchor(existing)
            ):
                kept[index] = candidate
                skip = True
                break
            if not (candidate_categories & existing_categories):
                continue
            overlap = len(candidate_tokens & existing_tokens) / max(1, min(len(candidate_tokens), len(existing_tokens)))
            shared_features = candidate_features & existing_features
            if overlap >= 0.7:
                skip = True
                break
            if "adverse" in candidate_categories and "adverse" in existing_categories and len(shared_features) >= 3:
                skip = True
                break
            if "report" in candidate_categories and "report" in existing_categories and "accommodation" in shared_features and len(shared_features) >= 2:
                skip = True
                break
            if "policy_process" in candidate_categories and "policy_process" in existing_categories:
                if (
                    "denial_action" in candidate_features
                    and "denial_action" in existing_features
                    and "process_violation" in candidate_features
                    and "process_violation" not in existing_features
                ):
                    kept[index] = candidate
                    skip = True
                    break
                if "denial_action" in candidate_features ^ existing_features:
                    continue
                if (
                    "process_violation" in candidate_features
                    and "process_violation" not in existing_features
                    and len(shared_features & {"notice", "review_process"}) >= 1
                ):
                    kept[index] = candidate
                    skip = True
                    break
                if "process_violation" in shared_features and len(shared_features & {"notice", "review_process", "process_violation"}) >= 2:
                    skip = True
                    break
                if overlap >= 0.55 and len(shared_features & {"notice", "review_process"}) >= 1:
                    skip = True
                    break
        if not skip:
            kept.append(candidate)
    return kept

def _build_concrete_sequence_allegation(self, allegations: List[str]) -> str:
    if not allegations:
        return ""
    dated_events: Dict[str, tuple[str, str]] = {}
    for item in allegations:
        text = str(item or "").strip()
        lowered = text.lower()
        if not text or not _contains_date_anchor(text):
            continue
        date_text, clause = _extract_dated_event_clause(text)
        if not date_text or not clause:
            continue
        if any(
            marker in lowered
            for marker in (
                "grievance request",
                "requested a grievance hearing",
                "requested review",
                "review request",
                "submitted a grievance",
                "informal review request",
            )
        ):
            dated_events.setdefault("review_request", (date_text, clause))
            continue
        if any(
            marker in lowered
            for marker in (
                "review decision",
                "hearing outcome",
                "final decision",
                "issued the review decision",
                "issued the decision",
            )
        ):
            dated_events.setdefault("review_decision", (date_text, clause))
            continue
        if (
            "denial notice" in lowered
            or ("written notice" in lowered and "decision denying assistance" in lowered)
            or ("sent plaintiff" in lowered and "notice" in lowered)
        ):
            dated_events.setdefault("notice", (date_text, clause))

    ordered_segments = []
    for key in ("notice", "review_request", "review_decision"):
        if key not in dated_events:
            continue
        date_text, clause = dated_events[key]
        ordered_segments.append(f"on {date_text}, {clause}")
    if len(ordered_segments) < 2:
        return ""
    return f"The chronology shows that {_join_chronology_segments(ordered_segments)}."

def _build_missing_detail_allegations(
    self,
    allegations: List[str],
    source_allegations: Optional[List[str]] = None,
) -> List[str]:
    source_pool = [str(item or "").strip() for item in (source_allegations or allegations) if str(item or "").strip()]
    if not allegations and not source_pool:
        return []
    priority_email_count = sum(1 for line in source_pool if self._is_priority_email_timeline_allegation(line))
    if priority_email_count >= 3:
        concrete_sequence = self._build_concrete_sequence_allegation(source_pool)
        return [concrete_sequence] if concrete_sequence else []
    combined = " ".join(source_pool or [str(item or "") for item in allegations])
    lowered = combined.lower()
    references_notice = "notice" in lowered
    references_review = any(token in lowered for token in ("informal review", "hearing", "grievance", "appeal"))
    actor_label = self._infer_actor_label_from_allegations(source_pool or allegations)

    fallbacks: List[str] = []
    if not any(_contains_hearing_timing_marker(line) for line in source_pool):
        if references_review:
            fallbacks.append(
                f"The present record indicates that Plaintiff sought review of the challenged action, but the exact date of {self._actor_possessive_label(actor_label)} hearing or review request remains to be confirmed."
            )
        else:
            fallbacks.append(
                "The present record indicates that Plaintiff challenged the adverse action, but the exact date of that request for review remains to be confirmed."
            )
    if not any(_contains_response_date_marker(line) for line in source_pool):
        if references_notice and references_review:
            fallbacks.append(
                f"The current record further indicates deficiencies in {actor_label}'s notice and review process, although the exact dates of the notice, response, and final decision have not yet been confirmed."
            )
        elif references_notice:
            fallbacks.append(
                f"The current record indicates that {actor_label} issued or should have issued written notice, but the exact notice and response dates have not yet been confirmed."
            )
    if not any(_contains_staff_identity_marker(line) for line in source_pool):
        if references_notice or references_review:
            fallbacks.append(
                f"The present record does not yet identify by name the official at {actor_label} who issued the notice or handled Plaintiff's request for review."
            )
        else:
            fallbacks.append(
                f"The present record does not yet identify by name the responsible {actor_label} decisionmaker."
            )
    if not any(_contains_sequence_timing_marker(line) for line in source_pool):
        concrete_sequence = self._build_concrete_sequence_allegation(source_pool)
        if concrete_sequence:
            fallbacks.append(concrete_sequence)
        else:
            fallbacks.append(
                "The current chronology indicates that the protected activity, challenged notice, and resulting adverse treatment occurred in close sequence, although the precise intervals still require confirmation."
            )
    return fallbacks

def _build_policy_process_allegations(
    self,
    allegations: List[str],
    source_allegations: Optional[List[str]] = None,
) -> List[str]:
    source_pool = [str(item or "").strip() for item in (source_allegations or allegations) if str(item or "").strip()]
    if not allegations and not source_pool:
        return []
    combined = " ".join(source_pool or [str(item or "") for item in allegations])
    lowered = combined.lower()
    references_notice = "written notice" in lowered or "notice to the applicant" in lowered or "notice" in lowered
    references_review = any(token in lowered for token in ("informal review", "grievance", "appeal", "hearing"))
    references_denial = any(
        token in lowered
        for token in ("denying assistance", "denial notice", "denied assistance", "loss of assistance", "termination", "voucher")
    )
    actor_label = self._infer_actor_label_from_allegations(source_pool or allegations)

    case_specific_adverse_clause = ""
    for text in source_pool:
        lowered_text = text.lower()
        if not _contains_date_anchor(text):
            continue
        if any(
            token in lowered_text
            for token in ("denial notice", "denied assistance", "denying assistance", "loss of assistance", "termination")
        ):
            case_specific_adverse_clause = text.rstrip(".!?")
            break

    adverse_action_phrase = "denied Plaintiff housing assistance, or maintained the challenged loss of assistance"
    if "denial notice" in lowered:
        adverse_action_phrase = "issued a denial notice and denied Plaintiff housing assistance"
    elif "denying assistance" in lowered or "denied assistance" in lowered:
        adverse_action_phrase = "issued or maintained a denial of assistance"
    elif "loss of assistance" in lowered:
        adverse_action_phrase = "maintained the challenged loss of assistance"
    elif "termination" in lowered:
        adverse_action_phrase = "terminated or threatened to terminate Plaintiff's assistance"

    synthesized: List[str] = []
    if references_notice and not any(
        "without providing the prompt written notice required" in str(item).lower()
        for item in allegations
    ) and not any(
        "notice to the applicant requires prompt written notice" in str(item).lower()
        or "requires prompt written notice of a decision denying assistance" in str(item).lower()
        for item in allegations
    ):
        synthesized.append(
            f"Plaintiff alleges that {actor_label} took or maintained the challenged adverse housing action without providing the prompt written notice required for a decision denying assistance."
        )
    if references_review and not any(
        "failed to provide the informal review" in str(item).lower()
        or "failed to provide the grievance" in str(item).lower()
        or "failed to provide the appeal" in str(item).lower()
        for item in allegations
    ):
        synthesized.append(
            f"Plaintiff further alleges that {actor_label} failed to provide the informal review, grievance, or appeal process that should have accompanied the challenged action."
        )
    if references_denial and not any(
        "without the notice and review protections described in the governing process" in str(item).lower()
        or "without providing the prompt written notice required" in str(item).lower()
        for item in allegations
    ):
        if case_specific_adverse_clause:
            lead_in = "Plaintiff further alleges that"
            normalized_clause = case_specific_adverse_clause
            if re.match(r"^(On|By|After|Before|During)\b", case_specific_adverse_clause):
                normalized_clause = case_specific_adverse_clause[0].lower() + case_specific_adverse_clause[1:]
            synthesized.append(
                f"{lead_in} {normalized_clause}, without the notice and review protections described in the governing process."
            )
        else:
            synthesized.append(
                f"Plaintiff further alleges that {actor_label} {adverse_action_phrase} without the notice and review protections described in the governing process."
            )
    return synthesized

def _prune_redundant_policy_rule_allegations(self, allegations: List[str]) -> List[str]:
    if not allegations:
        return []
    lowered_all = [str(item or "").lower() for item in allegations]
    has_notice_process_allegation = any(
        "without the notice and review protections described in the governing process" in item
        or "failed to provide the informal review" in item
        for item in lowered_all
    )
    has_chronology = any(item.startswith("the chronology shows that ") for item in lowered_all)
    if not (has_notice_process_allegation and has_chronology):
        return allegations

    pruned: List[str] = []
    for item in allegations:
        lowered = str(item or "").lower()
        if (
            "notice to the applicant requires prompt written notice of a decision denying assistance" in lowered
        ):
            continue
        pruned.append(item)
    return pruned or allegations

def _build_factual_allegations(
    self,
    *,
    summary_of_facts: Any,
    claims_for_relief: List[Dict[str, Any]],
) -> List[str]:
    base_allegations = self._merge_email_attachment_follow_on_allegations(
        list(self._expand_allegation_sources(summary_of_facts, limit=14))
    )
    priority_email_allegations = [
        item for item in base_allegations if self._is_priority_email_timeline_allegation(item)
    ]
    allegations = list(priority_email_allegations)
    for item in self._synthesize_narrative_allegations(base_allegations):
        if item.lower() not in {entry.lower() for entry in allegations}:
            allegations.append(item)
    for item in self._prune_subsumed_narrative_clauses(base_allegations):
        if item.lower() not in {entry.lower() for entry in allegations}:
            allegations.append(item)
    seen = {entry.lower() for entry in allegations}

    for claim in _coerce_list(claims_for_relief):
        if not isinstance(claim, dict):
            continue
        count_title = str(claim.get("count_title") or claim.get("claim_type") or "Claim").strip()
        for fact in self._expand_allegation_sources(claim.get("supporting_facts", []), limit=10):
            if not fact:
                continue
            if self._is_priority_email_timeline_allegation(fact):
                continue
            if str(fact or "").strip().lower().startswith("one of those clackamas emails included the attachment "):
                continue
            if self._is_near_duplicate_allegation(fact, allegations):
                continue
            prefixed_fact = fact
            if count_title and not fact.lower().startswith("as to ") and fact.lower() not in seen:
                lowered = fact
                if not re.match(r"^(Plaintiff|Defendant)\b", fact):
                    lowered = fact[0].lower() + fact[1:] if len(fact) > 1 and fact[0].isalpha() else fact
                prefixed_fact = f"As to {count_title}, {lowered}"
                if not prefixed_fact.endswith((".", "?", "!")):
                    prefixed_fact = f"{prefixed_fact}."
            key = prefixed_fact.lower()
            if key in seen:
                continue
            seen.add(key)
            allegations.append(prefixed_fact)
            if len(allegations) >= 24:
                return self._prune_near_duplicate_allegations(allegations)

    pruned = self._prune_near_duplicate_allegations(allegations)
    for item in self._build_email_timeline_issue_allegations(pruned, base_allegations):
        if item.lower() not in {entry.lower() for entry in pruned}:
            pruned.append(item)
    pruned.extend(self._build_policy_process_allegations(pruned, base_allegations))
    pruned.extend(self._build_missing_detail_allegations(pruned, base_allegations))
    pruned = self._prune_near_duplicate_allegations(pruned)
    pruned = self._prune_redundant_policy_rule_allegations(pruned)
    return pruned[:24] or ["Additional factual development is required before filing."]

def _build_factual_allegation_entries(
    self,
    *,
    summary_fact_entries: List[Dict[str, Any]],
    claims_for_relief: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    allegation_texts = self._build_factual_allegations(
        summary_of_facts=[entry.get("text") for entry in summary_fact_entries if isinstance(entry, dict)],
        claims_for_relief=claims_for_relief,
    )
    source_entries: List[Dict[str, Any]] = []
    source_entries.extend([dict(entry) for entry in summary_fact_entries if isinstance(entry, dict)])
    for claim in _coerce_list(claims_for_relief):
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("claim_type") or "").strip()
        for entry in _coerce_list(claim.get("supporting_fact_entries")):
            if not isinstance(entry, dict):
                continue
            claim_entry = dict(entry)
            if claim_type:
                claim_entry["claim_types"] = _normalize_identifier_list(
                    list(claim_entry.get("claim_types") or []) + [claim_type]
                )
            source_entries.append(claim_entry)

    entries: List[Dict[str, Any]] = []
    for text in allegation_texts:
        matched_entries = self._match_document_source_entries(text, source_entries)
        if "failed to provide the informal review" in str(text or "").lower():
            matched_entries = self._enrich_review_process_fact_matches(
                matched_entries=matched_entries,
                source_entries=source_entries,
            )
        if str(text or "").lower().startswith("the chronology shows that "):
            matched_entries = self._enrich_chronology_fact_matches(
                matched_entries=matched_entries,
                source_entries=source_entries,
            )
        entries.append(
            {
                "text": text,
                "fact_ids": _normalize_identifier_list(
                    [
                        fact_id
                        for entry in matched_entries
                        for fact_id in _coerce_list(entry.get("fact_ids"))
                    ]
                ),
                "source_artifact_ids": _normalize_identifier_list(
                    [
                        artifact_id
                        for entry in matched_entries
                        for artifact_id in _coerce_list(entry.get("source_artifact_ids"))
                    ]
                ),
                "claim_types": _normalize_identifier_list(
                    [
                        claim_type
                        for entry in matched_entries
                        for claim_type in _coerce_list(entry.get("claim_types"))
                    ]
                ),
                "claim_element_ids": _normalize_identifier_list(
                    [
                        claim_element_id
                        for entry in matched_entries
                        for claim_element_id in _coerce_list(entry.get("claim_element_ids"))
                    ]
                ),
                "support_trace_ids": _normalize_identifier_list(
                    [
                        trace_id
                        for entry in matched_entries
                        for trace_id in _coerce_list(entry.get("support_trace_ids"))
                    ]
                ),
                "source_kind": "factual_allegation",
            }
        )
    return entries

def _attach_allegation_references(self, draft: Dict[str, Any]) -> None:
    allegation_lines = self._normalize_text_lines(
        draft.get("factual_allegations") or draft.get("summary_of_facts", [])
    )
    allegation_entries = self._align_entries_to_lines(
        draft.get("factual_allegation_entries"),
        allegation_lines,
    )
    paragraph_entries = [
        {
            "number": index,
            "text": text,
            "fact_ids": allegation_entries[index - 1].get("fact_ids", []),
            "source_artifact_ids": allegation_entries[index - 1].get("source_artifact_ids", []),
            "claim_types": allegation_entries[index - 1].get("claim_types", []),
            "claim_element_ids": allegation_entries[index - 1].get("claim_element_ids", []),
            "support_trace_ids": allegation_entries[index - 1].get("support_trace_ids", []),
            "source_kind": allegation_entries[index - 1].get("source_kind"),
            "document_focus": (
                dict(allegation_entries[index - 1].get("document_focus") or {})
                if isinstance(allegation_entries[index - 1].get("document_focus"), dict)
                else {}
            ),
            "document_focus_priority_rank": allegation_entries[index - 1].get("document_focus_priority_rank"),
        }
        for index, text in enumerate(allegation_lines, start=1)
    ]
    paragraph_entries = self._annotate_entries_with_exhibits(
        paragraph_entries,
        draft.get("exhibits") if isinstance(draft.get("exhibits"), list) else [],
    )
    allegation_entries = [
        {
            **dict(allegation_entries[index]),
            "text": paragraph_entries[index].get("text"),
            "exhibit_label": paragraph_entries[index].get("exhibit_label"),
        }
        for index in range(min(len(allegation_entries), len(paragraph_entries)))
    ]
    allegation_lines = [str(entry.get("text") or "").strip() for entry in paragraph_entries if str(entry.get("text") or "").strip()]
    draft["factual_allegations"] = allegation_lines
    draft["factual_allegation_entries"] = allegation_entries
    draft["factual_allegation_paragraphs"] = paragraph_entries
    draft["factual_allegation_groups"] = self._build_factual_allegation_groups(paragraph_entries)

    claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim["supporting_fact_provenance"] = self._build_claim_supporting_fact_provenance(
            claim=claim,
        )
        claim["allegation_references"] = self._select_allegation_references_for_claim(
            claim=claim,
            allegation_paragraphs=paragraph_entries,
        )
    draft["document_provenance_summary"] = self._build_document_provenance_summary(draft)

def _grouped_allegation_text_lines(self, draft: Dict[str, Any]) -> List[str]:
    groups = draft.get("factual_allegation_groups") if isinstance(draft.get("factual_allegation_groups"), list) else []
    if not groups:
        return self._numbered_lines(draft.get("factual_allegations") or draft.get("summary_of_facts", []))

    lines: List[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        title = str(group.get("title") or "").strip()
        paragraphs = group.get("paragraphs") if isinstance(group.get("paragraphs"), list) else []
        if not paragraphs:
            continue
        if title:
            lines.append(self._format_group_heading(title, paragraphs))
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                continue
            number = paragraph.get("number")
            text = str(paragraph.get("text") or "").strip()
            if text:
                lines.append(f"{number}. {text}" if number else text)
    return lines

def _select_allegation_references_for_claim(
    self,
    *,
    claim: Dict[str, Any],
    allegation_paragraphs: List[Dict[str, Any]],
) -> List[int]:
    references: List[int] = []
    supporting_facts = self._normalize_text_lines(claim.get("supporting_facts", []))
    supporting_entries = self._align_entries_to_lines(
        claim.get("supporting_fact_entries"),
        supporting_facts,
    )
    count_title = str(claim.get("count_title") or claim.get("claim_type") or "").strip().lower()

    for fact, entry in zip(supporting_facts, supporting_entries):
        fact_tokens = self._text_tokens(fact)
        if not fact_tokens:
            continue
        best_number: Optional[int] = None
        best_score = 0
        fact_lower = fact.lower()
        fact_ids = set(_normalize_identifier_list(entry.get("fact_ids") or []))
        for paragraph in allegation_paragraphs:
            if not isinstance(paragraph, dict):
                continue
            paragraph_text = str(paragraph.get("text") or "").strip()
            paragraph_lower = paragraph_text.lower()
            paragraph_tokens = self._text_tokens(paragraph_text)
            score = len(fact_tokens & paragraph_tokens)
            if fact_lower in paragraph_lower:
                score += 100
            paragraph_fact_ids = set(_normalize_identifier_list(paragraph.get("fact_ids") or []))
            if fact_ids and paragraph_fact_ids and fact_ids & paragraph_fact_ids:
                score += 50
            if count_title and count_title in paragraph_lower:
                score += 5
            if score > best_score:
                best_score = score
                best_number = int(paragraph.get("number", 0) or 0)
        if best_number and best_number not in references:
            references.append(best_number)
            if len(references) >= 6:
                break

    if references:
        return references

    fallback = []
    for paragraph in allegation_paragraphs:
        paragraph_text = str(paragraph.get("text") or "").lower()
        if count_title and count_title in paragraph_text:
            fallback.append(int(paragraph.get("number", 0) or 0))
    return fallback[:4]
