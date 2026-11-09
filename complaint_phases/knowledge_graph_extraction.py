"""Entity and relationship extraction delegated from KnowledgeGraphBuilder."""

from __future__ import annotations

from typing import (
    Mapping,
)

from complaint_phases.knowledge_graph import (
    locate_unique_byte_span,
    re,
)


def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
    """
    Extract entities from text using LLM or rule-based extraction.

    This is a simplified implementation. In production, this would use
    the mediator's LLM backend to do sophisticated entity extraction.
    """
    entities = []
    seen: Set[Tuple[str, str]] = set()

    def add_entity(entity: Dict[str, Any]) -> None:
        if not isinstance(entity, dict):
            return
        name = (entity.get("name") or "").strip()
        etype = (entity.get("type") or "").strip()
        if not name or not etype:
            return
        if not isinstance(entity.get("source_span"), Mapping) and etype.lower() in {"date", "person", "organization"}:
            lookup = locate_unique_byte_span(text or "", name)
            if lookup.deficiency == "" and lookup.start is not None and lookup.end is not None:
                entity["source_span"] = {
                    "start": lookup.start,
                    "end": lookup.end,
                    "text": lookup.text,
                }
        key = (etype.lower(), name.lower())
        if key in seen:
            return
        seen.add(key)
        entities.append(entity)

    def short_description(text_value: str, limit: int = 240) -> str:
        snippet = " ".join((text_value or "").strip().split())
        if len(snippet) > limit:
            return snippet[: limit - 3] + "..."
        return snippet

    lower_text = (text or "").lower()
    employment_context_terms = (
        'employer',
        'job',
        'work',
        'workplace',
        'supervisor',
        'manager',
        'hr',
        'human resources',
        'coworker',
        'company',
        'shift',
        'promotion',
    )
    housing_context_terms = (
        'landlord',
        'tenant',
        'lease',
        'apartment',
        'housing',
        'rent',
        'property manager',
        'property management',
        'evict',
        'unit',
        'section 8',
    )

    # For now, use simple keyword-based extraction
    # In production, this would use LLM prompts like:
    # "Extract all people, organizations, dates, locations, and claims from: {text}"

    # Extract simple entities (this is a placeholder)
    discrimination_terms = (
        'discrimination',
        'discriminated',
        'discriminatory',
        'harassment',
        'harassed',
    )
    if any(term in lower_text for term in discrimination_terms):
        employment_context = any(term in lower_text for term in employment_context_terms)
        housing_context = any(term in lower_text for term in housing_context_terms)
        if employment_context and not housing_context:
            claim_type = 'employment_discrimination'
            claim_name = 'Employment Discrimination Claim'
        elif housing_context and not employment_context:
            claim_type = 'housing_discrimination'
            claim_name = 'Housing Discrimination Claim'
        else:
            claim_type = 'discrimination'
            claim_name = 'Discrimination Claim'
        add_entity({
            'type': 'claim',
            'name': claim_name,
            'attributes': {
                'claim_type': claim_type,
                'description': short_description(text),
            },
            'confidence': 0.9
        })

    if any(term in lower_text for term in ['accommodation', 'accommodate', 'reasonable accommodation']):
        add_entity({
            'type': 'claim',
            'name': 'Accommodation Request',
            'attributes': {
                'claim_type': 'accommodation',
                'description': short_description(text),
            },
            'confidence': 0.8
        })

    if any(k in lower_text for k in ['denied', 'refused', 'rejected', 'declined']):
        add_entity({
            'type': 'claim',
            'name': 'Denial/Refusal Claim',
            'attributes': {
                'claim_type': 'denial',
                'description': short_description(text),
            },
            'confidence': 0.7
        })

    retaliation_terms = (
        'retaliation',
        'retaliated',
        'retaliatory',
        'retaliat',
    )
    retaliation_context_terms = (
        'complained',
        'reported',
        'grievance',
        'hr',
        'human resources',
        'requested accommodation',
        'whistlebl',
    )
    adverse_action_terms = (
        'fired',
        'terminated',
        'demoted',
        'suspended',
        'cut my hours',
        'reduced my hours',
        'evicted',
        'disciplined',
    )
    if (
        any(term in lower_text for term in retaliation_terms)
        or (
            any(term in lower_text for term in retaliation_context_terms)
            and any(term in lower_text for term in adverse_action_terms)
            and any(term in lower_text for term in ['after', 'because', 'later', 'soon after'])
        )
    ):
        add_entity({
            'type': 'claim',
            'name': 'Retaliation Claim',
            'attributes': {
                'claim_type': 'retaliation',
                'description': short_description(text),
            },
            'confidence': 0.85
        })

    if 'employer' in lower_text:
        add_entity({
            'type': 'organization',
            'name': 'Employer',
            'attributes': {'role': 'respondent'},
            'confidence': 0.7
        })

    if 'employee' in lower_text or 'complainant' in lower_text:
        add_entity({
            'type': 'person',
            'name': 'Complainant',
            'attributes': {'role': 'complainant'},
            'confidence': 0.9
        })

    # Housing/property management role heuristics
    if 'landlord' in lower_text:
        add_entity({
            'type': 'person',
            'name': 'Landlord',
            'attributes': {'role': 'landlord'},
            'confidence': 0.6
        })

    if any(k in lower_text for k in ['property management', 'property manager', 'management company', 'leasing office', 'housing authority', 'housing office']):
        add_entity({
            'type': 'organization',
            'name': 'Property Management',
            'attributes': {'role': 'respondent'},
            'confidence': 0.6
        })

    # Additional heuristic extraction for dates (timeline) and common claims
    date_patterns = [
        r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
        r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{4}\b',
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b(?:in|on|since|during|around|by|from)\s+(?:19|20)\d{2}\b',
    ]
    relative_patterns = [
        r'\b(?:today|yesterday|tonight|last night|this morning|this afternoon|this evening)\b',
        r'\b(?:last|this|next)\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        r'\b\d+\s+(?:day|week|month|year)s?\s+ago\b',
        r'\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|week|month|year)s?\s+ago\b',
        r'\b\d+\s+(?:day|week|month|year)s?\s+(?:after|before|later|earlier)\b',
        r'\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|week|month|year)s?\s+(?:after|before|later|earlier)\b',
    ]
    found_dates: set[str] = set()
    for pattern in date_patterns:
        for match in re.findall(pattern, text):
            found_dates.add(match.strip())
    for pattern in relative_patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            found_dates.add(match.strip())

    for date_str in found_dates:
        add_entity({
            'type': 'date',
            'name': date_str,
            'attributes': {},
            'confidence': 0.8
        })

    sentence_parts = [
        sentence.strip(" \t\r\n,;:-")
        for sentence in re.split(r'(?<=[.!?])\s+|[\r\n]+', text or '')
        if sentence and sentence.strip()
    ]

    def _extract_event_date_reference(text_value: str) -> Optional[str]:
        for pattern in date_patterns:
            match = re.search(pattern, text_value or '')
            if match:
                return match.group(0).strip()
        for pattern in relative_patterns:
            match = re.search(pattern, text_value or '', flags=re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None

    def add_timeline_event_fact(
        sentence: str,
        *,
        predicate_family: str,
        event_label: str,
        name_prefix: str,
        confidence: float,
    ) -> None:
        description = short_description(sentence)
        attributes: Dict[str, Any] = {
            'fact_type': 'timeline',
            'predicate_family': predicate_family,
            'event_label': event_label,
            'description': description,
        }
        event_date = _extract_event_date_reference(sentence)
        if event_date:
            attributes['event_date_or_range'] = event_date
        fact_record: Dict[str, Any] = {
            'type': 'fact',
            'name': f"{name_prefix}: {short_description(sentence, 60)}",
            'attributes': attributes,
            'confidence': confidence,
        }
        span_lookup = locate_unique_byte_span(text or "", sentence)
        if span_lookup.deficiency == "" and span_lookup.start is not None and span_lookup.end is not None:
            fact_record["source_span"] = {
                "start": span_lookup.start,
                "end": span_lookup.end,
                "text": span_lookup.text,
            }
        add_entity(fact_record)

    protected_activity_event_count = 0
    adverse_action_event_count = 0
    causation_event_count = 0
    notice_event_count = 0
    hearing_event_count = 0
    response_event_count = 0
    protected_activity_markers = (
        'complained',
        'complaint',
        'reported',
        'grievance',
        'hr',
        'human resources',
        'requested accommodation',
        'whistlebl',
    )
    notice_sentence_markers = (
        'notice',
        'letter',
        'email',
        'emailed',
        'text',
        'message',
        'voicemail',
        'mailed',
        'sent',
    )
    hearing_sentence_markers = (
        'hearing',
        'appeal',
        'grievance',
        'review',
    )
    hearing_request_markers = (
        'requested',
        'request',
        'asked for',
        'filed',
        'submitted',
        'sought',
    )
    response_sentence_markers = (
        'response',
        'responded',
        'reply',
        'replied',
        'denied',
        'approved',
        'ignored',
        'decision',
        'upheld',
        'rejected',
        'no response',
    )
    causation_markers = (
        'after',
        'because',
        'due to',
        'soon after',
        'in response to',
        'later',
    )
    for sentence in sentence_parts:
        lowered_sentence = sentence.lower()
        has_protected_marker = any(marker in lowered_sentence for marker in protected_activity_markers)
        has_adverse_marker = any(marker in lowered_sentence for marker in adverse_action_terms)
        has_causation_marker = any(marker in lowered_sentence for marker in causation_markers)
        if has_protected_marker:
            add_timeline_event_fact(
                sentence,
                predicate_family='protected_activity',
                event_label='Protected activity',
                name_prefix='Protected activity event',
                confidence=0.63,
            )
            protected_activity_event_count += 1
        if has_adverse_marker:
            add_timeline_event_fact(
                sentence,
                predicate_family='adverse_action',
                event_label='Adverse action',
                name_prefix='Adverse action event',
                confidence=0.63,
            )
            adverse_action_event_count += 1
        if has_causation_marker and (
            (has_protected_marker and has_adverse_marker)
            or (has_adverse_marker and any(marker in lower_text for marker in protected_activity_markers))
            or (has_protected_marker and any(marker in lower_text for marker in adverse_action_terms))
        ):
            add_timeline_event_fact(
                sentence,
                predicate_family='causation',
                event_label='Causation sequence',
                name_prefix='Retaliation causation event',
                confidence=0.64,
            )
            causation_event_count += 1
        if any(marker in lowered_sentence for marker in notice_sentence_markers):
            add_timeline_event_fact(
                sentence,
                predicate_family='notice_chain',
                event_label='Notice communication',
                name_prefix='Notice event',
                confidence=0.62,
            )
            notice_event_count += 1
        if any(marker in lowered_sentence for marker in hearing_sentence_markers) and any(
            marker in lowered_sentence for marker in hearing_request_markers
        ):
            add_timeline_event_fact(
                sentence,
                predicate_family='hearing_process',
                event_label='Hearing request event',
                name_prefix='Hearing request event',
                confidence=0.64,
            )
            hearing_event_count += 1
        elif any(marker in lowered_sentence for marker in hearing_sentence_markers):
            add_timeline_event_fact(
                sentence,
                predicate_family='hearing_process',
                event_label='Hearing/appeal event',
                name_prefix='Hearing event',
                confidence=0.61,
            )
            hearing_event_count += 1
        if any(marker in lowered_sentence for marker in response_sentence_markers):
            add_timeline_event_fact(
                sentence,
                predicate_family='response_timeline',
                event_label='Response event',
                name_prefix='Response event',
                confidence=0.63,
            )
            response_event_count += 1

    # Add a termination-related claim if relevant keywords appear
    if 'terminated' in lower_text or 'fired' in lower_text:
        add_entity({
            'type': 'claim',
            'name': 'Termination Claim',
            'attributes': {
                'claim_type': 'termination',
                'description': short_description(text),
            },
            'confidence': 0.8
        })

    # Heuristic extraction for organization names
    org_candidates: Set[str] = set()
    org_suffixes = (
        r"(?:Inc\.?|LLC|Ltd\.?|Co\.?|Corp\.?|Corporation|Company|University|"
        r"Hospital|School|Department|Dept\.?|Agency|Clinic|Bank|Foundation|"
        r"Association|Partners|Group|Systems|Services)"
    )
    for match in re.findall(rf"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){{0,4}}\s+{org_suffixes})\b", text or ""):
        org_candidates.add(match.strip())

    for match in re.findall(r"\b(?:at|for|with|from)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4})\b", text or ""):
        org_candidates.add(match.strip())

    months = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    }
    banned = {"i", "we", "they", "he", "she", "it", "my", "our", "their", "the", "a", "an"}

    for candidate in sorted(org_candidates):
        cleaned = re.sub(r"[^\w&.\-\s]", "", candidate).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in banned or lowered in months:
            continue
        tokens = cleaned.split()
        if len(tokens) == 1 and len(cleaned) < 4:
            continue
        add_entity({
            'type': 'organization',
            'name': cleaned,
            'attributes': {'role': 'respondent'},
            'confidence': 0.6
        })

    # Evidence-related entities from common document/communication mentions
    evidence_keywords = {
        'email': 'Email communication',
        'emails': 'Email communication',
        'text message': 'Text messages',
        'texts': 'Text messages',
        'letter': 'Letter',
        'notice': 'Notice',
        'application': 'Application',
        'receipt': 'Receipt',
        'lease': 'Lease',
        'voicemail': 'Voicemail',
        'meeting notes': 'Meeting notes',
        'contract': 'Contract',
        'agreement': 'Agreement',
        'estimate': 'Estimate',
        'invoice': 'Invoice',
        'change order': 'Change order',
        'work order': 'Work order',
        'warranty': 'Warranty',
        'screening criteria': 'Screening criteria',
        'policy': 'Policy',
        'photo': 'Photos',
        'photos': 'Photos',
        'picture': 'Photos',
        'video': 'Video',
        'payment': 'Payment record',
        'check': 'Payment record',
        'bank statement': 'Bank statement',
    }
    for keyword, label in evidence_keywords.items():
        if keyword in lower_text:
            add_entity({
                'type': 'evidence',
                'name': label,
                'attributes': {
                    'evidence_type': label.lower(),
                    'description': short_description(text),
                },
                'confidence': 0.55
            })

    impact_keywords = [
        'harm',
        'damages',
        'injury',
        'emotional',
        'stress',
        'anxiety',
        'financial',
        'lost wages',
        'lost pay',
        'missed work',
        'out of pocket',
        'medical',
        'evicted',
        'unsafe',
        'retaliation',
    ]
    if any(k in lower_text for k in impact_keywords):
        add_entity({
            'type': 'fact',
            'name': f"Impact: {short_description(text, 60)}",
            'attributes': {
                'fact_type': 'impact',
                'description': short_description(text),
            },
            'confidence': 0.55
        })

    remedy_keywords = [
        'seeking',
        'seek',
        'would like',
        'looking for',
        'request',
        'asking for',
        'refund',
        'reimbursement',
        'compensation',
        'back pay',
        'repair',
        'fix',
        'replacement',
        'apology',
        'policy change',
        'accommodation',
    ]
    if any(k in lower_text for k in remedy_keywords):
        add_entity({
            'type': 'fact',
            'name': f"Requested remedy: {short_description(text, 60)}",
            'attributes': {
                'fact_type': 'remedy',
                'description': short_description(text),
            },
            'confidence': 0.55
        })

    if hearing_event_count == 0 and any(token in lower_text for token in ('hearing', 'appeal', 'grievance')):
        add_entity({
            'type': 'fact',
            'name': 'Hearing or appeal process event',
            'attributes': {
                'fact_type': 'timeline',
                'predicate_family': 'hearing_process',
                'event_label': 'Hearing/appeal event',
                'description': short_description(text),
            },
            'confidence': 0.58,
        })
    if notice_event_count == 0 and any(token in lower_text for token in ('notice', 'letter', 'email', 'message', 'text', 'voicemail')):
        add_entity({
            'type': 'fact',
            'name': 'Written notice or communication event',
            'attributes': {
                'fact_type': 'timeline',
                'predicate_family': 'notice_chain',
                'event_label': 'Notice communication',
                'description': short_description(text),
            },
            'confidence': 0.58,
        })
    if response_event_count == 0 and any(token in lower_text for token in ('response', 'responded', 'replied', 'denied', 'approved', 'ignored', 'no response')):
        add_entity({
            'type': 'fact',
            'name': 'Agency/employer response event',
            'attributes': {
                'fact_type': 'timeline',
                'predicate_family': 'response_timeline',
                'event_label': 'Response event',
                'description': short_description(text),
            },
            'confidence': 0.58,
        })
    if protected_activity_event_count == 0 and any(term in lower_text for term in retaliation_context_terms):
        add_entity({
            'type': 'fact',
            'name': 'Protected activity event',
            'attributes': {
                'fact_type': 'timeline',
                'predicate_family': 'protected_activity',
                'event_label': 'Protected activity',
                'description': short_description(text),
            },
            'confidence': 0.6,
        })
    if adverse_action_event_count == 0 and any(term in lower_text for term in adverse_action_terms):
        add_entity({
            'type': 'fact',
            'name': 'Adverse action event',
            'attributes': {
                'fact_type': 'timeline',
                'predicate_family': 'adverse_action',
                'event_label': 'Adverse action',
                'description': short_description(text),
            },
            'confidence': 0.6,
        })
    if causation_event_count == 0 and any(token in lower_text for token in ('after', 'because', 'due to', 'soon after', 'in response to', 'later')):
        add_entity({
            'type': 'fact',
            'name': 'Retaliation causation link',
            'attributes': {
                'fact_type': 'timeline',
                'predicate_family': 'causation',
                'event_label': 'Causation sequence',
                'description': short_description(text),
            },
            'confidence': 0.6,
        })

    # If we still don't have any organization, add a generic employer when text implies one.
    has_org = any(e.get("type") == "organization" for e in entities if isinstance(e, dict))
    if not has_org and any(k in lower_text for k in ["company", "workplace", "organization", "business", "agency", "department", "school", "university", "hospital", "clinic"]):
        add_entity({
            'type': 'organization',
            'name': 'Organization',
            'attributes': {'role': 'respondent'},
            'confidence': 0.5
        })

    # Heuristic extraction for named individuals in role contexts
    role_keywords = (
        r"manager|supervisor|boss|coworker|co-worker|hr|human resources|director|"
        r"owner|principal|teacher|professor|doctor|nurse|attorney|lawyer|agent|"
        r"officer|landlord|neighbor|representative"
    )
    for match in re.finditer(
        rf"\b(?:my|the|a|an)\s+(?P<role>{role_keywords})\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})(?=\s+(?:denied|approved|replied|responded|emailed|called|told|said|was|is|did)\b|[.,;]|$)",
        text or "",
        re.IGNORECASE
    ):
        role = (match.group("role") or "").strip().lower()
        name = (match.group("name") or "").strip()
        if name and all(part[:1].isupper() for part in name.split() if part):
            add_entity({
                'type': 'person',
                'name': name,
                'attributes': {'role': role},
                'confidence': 0.7
            })

    expanded_title_keywords = (
        r"regional manager|property manager|case manager|program manager|leasing manager|"
        r"hearing officer|appeals officer|hr manager|human resources manager|director|"
        r"assistant director|supervisor|coordinator|specialist|officer|landlord|owner"
    )
    for match in re.finditer(
        rf"\b(?P<title>{expanded_title_keywords})\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})(?=\s+(?:denied|approved|replied|responded|emailed|called|told|said|was|is|did)\b|[.,;]|$)",
        text or "",
        re.IGNORECASE,
    ):
        title = (match.group("title") or "").strip().lower()
        name = (match.group("name") or "").strip()
        if not name or not title or not all(part[:1].isupper() for part in name.split() if part):
            continue
        add_entity({
            'type': 'person',
            'name': name,
            'attributes': {'role': title},
            'confidence': 0.74,
        })

    for match in re.finditer(
        rf"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})\s+(?:was|is|served as|acted as|worked as)\s+(?:the\s+)?(?P<title>{expanded_title_keywords})\b",
        text or "",
        re.IGNORECASE,
    ):
        name = (match.group("name") or "").strip()
        title = (match.group("title") or "").strip().lower()
        if not name or not title or not all(part[:1].isupper() for part in name.split() if part):
            continue
        add_entity({
            'type': 'person',
            'name': name,
            'attributes': {'role': title},
            'confidence': 0.72,
        })

    for match in re.finditer(
        r"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(?P<title>[A-Za-z][A-Za-z\s/&-]{2,60})\b",
        text or "",
    ):
        name = (match.group("name") or "").strip()
        title = (match.group("title") or "").strip().lower()
        if not name or not title:
            continue
        add_entity({
            'type': 'person',
            'name': name,
            'attributes': {'role': title},
            'confidence': 0.68
        })

    # Use LLM if available
    if self.mediator:
        llm_entities = self._llm_extract_entities(text)
        for ent in llm_entities:
            if isinstance(ent, dict):
                add_entity(ent)

    # Fallback: ensure we have at least one claim to drive downstream graphs.
    # Many parts of the pipeline (dependency graph, denoiser questions) assume
    # there's at least one claim-like entity.
    has_claim = any(e.get("type") == "claim" for e in entities if isinstance(e, dict))
    if not has_claim:
        description = short_description(text)
        add_entity(
            {
                "type": "claim",
                "name": "Complaint Claim",
                "attributes": {
                    "claim_type": "unknown",
                    "description": description,
                },
                "confidence": 0.5,
            }
        )

    return self._apply_entity_actor_critic(text, entities)
def _extract_relationships(self, text: str, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
    """
    Extract relationships between entities.

    This is a simplified implementation. In production, this would use
    the mediator's LLM backend.
    """
    relationships = []

    # Find entities to relate
    persons = graph.get_entities_by_type('person')
    orgs = graph.get_entities_by_type('organization')
    claims = graph.get_entities_by_type('claim')

    # Create employment relationships
    for person in persons:
        for org in orgs:
            if (
                'employer' in org.name.lower()
                or org.attributes.get('role') == 'respondent'
            ):
                relationships.append({
                    'source_id': person.id,
                    'target_id': org.id,
                    'type': 'employed_by',
                    'confidence': 0.7
                })

    # Link claims to complainants
    for claim in claims:
        for person in persons:
            if 'complainant' in person.attributes.get('role', '').lower():
                relationships.append({
                    'source_id': person.id,
                    'target_id': claim.id,
                    'type': 'makes_claim',
                    'confidence': 0.9
                })

    # Link claims to respondent organizations when unambiguous
    if claims and orgs:
        if len(claims) == 1:
            claim = claims[0]
            for org in orgs:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': org.id,
                    'type': 'involves',
                    'confidence': 0.6
                })
        elif len(orgs) == 1:
            org = orgs[0]
            for claim in claims:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': org.id,
                    'type': 'involves',
                    'confidence': 0.6
                })

    # Link claims to respondent-role people when unambiguous
    respondent_roles = {'manager', 'supervisor', 'boss', 'owner', 'landlord', 'hr', 'human resources'}
    respondent_people = [
        person for person in persons
        if person.attributes.get('role', '').lower() in respondent_roles
    ]
    if claims and respondent_people:
        if len(claims) == 1:
            claim = claims[0]
            for person in respondent_people:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': person.id,
                    'type': 'involves',
                    'confidence': 0.6
                })
        elif len(respondent_people) == 1:
            person = respondent_people[0]
            for claim in claims:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': person.id,
                    'type': 'involves',
                    'confidence': 0.6
                })

    # Link claims to extracted dates to build a timeline
    dates = graph.get_entities_by_type('date')
    for claim in claims:
        for date_ent in dates:
            relationships.append({
                'source_id': claim.id,
                'target_id': date_ent.id,
                'type': 'occurred_on',
                'confidence': 0.6
            })

    # Add explicit causation/sequencing links for retaliation contexts.
    retaliation_claims = [
        claim for claim in claims
        if str((claim.attributes or {}).get('claim_type') or '').strip().lower() == 'retaliation'
    ]
    if retaliation_claims:
        fact_entities = graph.get_entities_by_type('fact')
        protected_activity_facts = [
            fact for fact in fact_entities
            if str((fact.attributes or {}).get('predicate_family') or '').strip().lower() == 'protected_activity'
        ]
        adverse_action_facts = [
            fact for fact in fact_entities
            if str((fact.attributes or {}).get('predicate_family') or '').strip().lower() == 'adverse_action'
        ]
        for protected_fact in protected_activity_facts:
            for adverse_fact in adverse_action_facts:
                relationships.append({
                    'source_id': adverse_fact.id,
                    'target_id': protected_fact.id,
                    'type': 'follows_protected_activity',
                    'confidence': 0.55,
                })
                relationships.append({
                    'source_id': adverse_fact.id,
                    'target_id': protected_fact.id,
                    'type': 'occurred_after',
                    'confidence': 0.52,
                })
        if any(token in (text or '').lower() for token in ('because', 'due to', 'in response to', 'soon after', 'after')):
            for claim in retaliation_claims:
                for fact in protected_activity_facts + adverse_action_facts:
                    relationships.append({
                        'source_id': claim.id,
                        'target_id': fact.id,
                        'type': 'causal_link',
                        'confidence': 0.5,
                    })

    # Link claims to evidence entities when unambiguous
    evidence_entities = graph.get_entities_by_type('evidence')
    if claims and evidence_entities:
        if len(claims) == 1:
            claim = claims[0]
            for evidence in evidence_entities:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': evidence.id,
                    'type': 'supported_by',
                    'confidence': 0.55
                })
        elif len(evidence_entities) == 1:
            evidence = evidence_entities[0]
            for claim in claims:
                relationships.append({
                    'source_id': claim.id,
                    'target_id': evidence.id,
                    'type': 'supported_by',
                    'confidence': 0.55
                })

    # Link evidence to a single respondent party when unambiguous.
    respondent_orgs = [
        org for org in orgs
        if org.attributes.get('role') == 'respondent' or 'employer' in org.name.lower()
    ]
    if evidence_entities:
        if len(respondent_orgs) == 1:
            org = respondent_orgs[0]
            for evidence in evidence_entities:
                relationships.append({
                    'source_id': evidence.id,
                    'target_id': org.id,
                    'type': 'associated_with',
                    'confidence': 0.5
                })
        elif len(respondent_people) == 1:
            person = respondent_people[0]
            for evidence in evidence_entities:
                relationships.append({
                    'source_id': evidence.id,
                    'target_id': person.id,
                    'type': 'associated_with',
                    'confidence': 0.5
                })

    # Add a communication edge when evidence suggests contact and parties are clear.
    complainants = [
        person for person in persons
        if 'complainant' in person.attributes.get('role', '').lower()
    ]
    if evidence_entities and complainants:
        if len(respondent_orgs) == 1:
            org = respondent_orgs[0]
            for complainant in complainants:
                relationships.append({
                    'source_id': complainant.id,
                    'target_id': org.id,
                    'type': 'communicated_with',
                    'confidence': 0.55
                })
        elif len(respondent_people) == 1:
            person = respondent_people[0]
            for complainant in complainants:
                relationships.append({
                    'source_id': complainant.id,
                    'target_id': person.id,
                    'type': 'communicated_with',
                    'confidence': 0.55
                })

    # Use LLM if available
    if self.mediator:
        llm_rels = self._llm_extract_relationships(text, graph)
        for rel in llm_rels:
            if not isinstance(rel, dict):
                continue
            if rel.get('source_id') and rel.get('target_id') and rel.get('type'):
                model_rel = dict(rel)
                model_rel["origin"] = "model"
                model_rel["record_type"] = "model_suggestion"
                relationships.append(model_rel)

    unique_relationships = {}
    for rel in relationships:
        key = (rel.get('source_id'), rel.get('target_id'), rel.get('type'))
        if not all(key):
            continue
        current = unique_relationships.get(key)
        if current is None or rel.get('confidence', 0.0) > current.get('confidence', 0.0):
            unique_relationships[key] = rel

    deduped_relationships = list(unique_relationships.values())
    prepared = self._apply_relationship_actor_critic(text, graph, deduped_relationships)
    for relationship in prepared:
        if isinstance(relationship, dict):
            relationship.setdefault("origin", "heuristic")
    return prepared
