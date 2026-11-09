"""Intake question selection delegated from AdversarialSession."""

from __future__ import annotations

from adversarial_harness.session import (
    Any,
    Dict,
    List,
    Set,
)

def _inject_intake_prompt_questions(
    cls,
    seed_complaint: Dict[str, Any],
    questions: Sequence[Any],
) -> List[Any]:
    existing_questions = list(questions or [])
    optimizer_context = cls._extract_actor_critic_intake_context(seed_complaint)
    weak_evidence_modalities = set(optimizer_context.get('weak_evidence_modalities') or set())
    weak_complaint_types = set(optimizer_context.get('weak_complaint_types') or set())
    key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
    unresolved_intake_objectives: Set[str] = set()
    unresolved_objective_keys = ('unresolved_intake_objectives', 'uncovered_objectives', 'focus_areas')
    context_payloads = [
        seed_complaint,
        key_facts,
        seed_complaint.get('_meta') if isinstance(seed_complaint.get('_meta'), dict) else None,
        seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint.get('actor_critic_optimizer'), dict) else None,
        seed_complaint.get('optimization_guidance') if isinstance(seed_complaint.get('optimization_guidance'), dict) else None,
        seed_complaint.get('document_optimization') if isinstance(seed_complaint.get('document_optimization'), dict) else None,
    ]
    for payload in context_payloads:
        if not isinstance(payload, dict):
            continue
        nested_payloads = [
            payload,
            payload.get('intake_priorities') if isinstance(payload.get('intake_priorities'), dict) else None,
            payload.get('document_handoff_summary') if isinstance(payload.get('document_handoff_summary'), dict) else None,
        ]
        for nested in nested_payloads:
            if not isinstance(nested, dict):
                continue
            for key in unresolved_objective_keys:
                for value in list(nested.get(key) or []):
                    objective = str(value or '').strip().lower()
                    if objective:
                        unresolved_intake_objectives.add(objective)
    signal_values = [
        float(value)
        for value in (
            optimizer_context.get('question_quality'),
            optimizer_context.get('empathy'),
            optimizer_context.get('efficiency'),
        )
        if isinstance(value, (int, float))
    ]
    stability_contexts = [
        seed_complaint,
        key_facts,
        seed_complaint.get('_meta') if isinstance(seed_complaint.get('_meta'), dict) else None,
        seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint.get('actor_critic_optimizer'), dict) else None,
        seed_complaint.get('optimization_guidance') if isinstance(seed_complaint.get('optimization_guidance'), dict) else None,
        seed_complaint.get('document_optimization') if isinstance(seed_complaint.get('document_optimization'), dict) else None,
        key_facts.get('actor_critic_optimizer') if isinstance(key_facts.get('actor_critic_optimizer'), dict) else None,
        key_facts.get('actor_critic_session_stability') if isinstance(key_facts.get('actor_critic_session_stability'), dict) else None,
    ]
    num_successful_sessions = None
    no_successful_sessions_hint = False
    explicit_recovery_hint = False
    for payload in stability_contexts:
        if not isinstance(payload, dict):
            continue
        for key in ('num_successful_sessions', 'successful_sessions', 'successful_runs'):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                num_successful_sessions = int(value)
        if bool(payload.get('no_successful_sessions')):
            no_successful_sessions_hint = True
        summary = str(payload.get('summary') or '').strip().lower()
        message = str(payload.get('message') or '').strip().lower()
        if 'no successful sessions' in summary or 'no successful sessions' in message:
            no_successful_sessions_hint = True

        stability_payload = payload.get('actor_critic_session_stability')
        if isinstance(stability_payload, dict):
            if str(stability_payload.get('mode') or '').strip().lower() == 'recovery':
                explicit_recovery_hint = True
            if str(stability_payload.get('reason') or '').strip().lower() == 'no_successful_sessions':
                no_successful_sessions_hint = True
            for key in ('num_successful_sessions', 'successful_sessions'):
                value = stability_payload.get(key)
                if isinstance(value, (int, float)):
                    num_successful_sessions = int(value)

        phase_signals = payload.get('phase_signal_context')
        if isinstance(phase_signals, dict):
            if bool(phase_signals.get('no_successful_sessions')):
                no_successful_sessions_hint = True
            for key in ('num_successful_sessions', 'successful_sessions'):
                value = phase_signals.get(key)
                if isinstance(value, (int, float)):
                    num_successful_sessions = int(value)

    no_successful_sessions = bool(no_successful_sessions_hint or num_successful_sessions == 0)
    # When actor-critic intake signals are missing/near-zero, preserve mediator
    # flow and only backfill a small number of missing objective probes.
    stability_recovery_mode = (
        no_successful_sessions
        or explicit_recovery_hint
        or (not signal_values)
        or max(signal_values) <= 0.05
    )
    strict_stability_mode = no_successful_sessions or explicit_recovery_hint
    stability_injection_budget = 4
    empty_questions_min_budget = 4
    limit_to_missing_objectives_in_stability = True
    one_probe_per_objective_in_stability = True
    signal_strength = max(signal_values) if signal_values else 0.0
    seed_boosted_probes: List[tuple[str, str]] = []
    supports_selection_criteria = cls._seed_supports_selection_criteria(seed_complaint)
    should_frontload_anchor_selection = bool(
        (
            supports_selection_criteria
            and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'})
        )
        or 'anchor_selection_criteria' in unresolved_intake_objectives
    )
    should_frontload_anchor_appeal_rights = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_appeal_rights' in unresolved_intake_objectives
    )
    should_frontload_anchor_grievance_hearing = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_grievance_hearing' in unresolved_intake_objectives
    )
    should_frontload_anchor_adverse_action = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_adverse_action' in unresolved_intake_objectives
        or 'adverse_action' in cls._extract_anchor_sections(seed_complaint)
    )
    should_frontload_hearing_request_timing = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'hearing_request_timing' in unresolved_intake_objectives
        or 'anchor_grievance_hearing' in unresolved_intake_objectives
    )
    should_frontload_staff_names_titles = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'staff_names_titles' in unresolved_intake_objectives
        or bool(cls._extract_anchor_sections(seed_complaint).intersection({'grievance_hearing', 'appeal_rights', 'adverse_action'}))
    )
    should_frontload_causation_sequence = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'causation_sequence' in unresolved_intake_objectives
    )

    if should_frontload_anchor_appeal_rights:
        seed_boosted_probes.append(
            (
                "What written appeal rights notice did you receive, when did you receive it, and what exact deadline and steps did it require?",
                "anchor_appeal_rights",
            )
        )
    if should_frontload_anchor_grievance_hearing:
        seed_boosted_probes.append(
            (
                "What grievance hearing rights were explained to you, when did you request a hearing, and what response or scheduling result did you get, including the request record and response notice date?",
                "anchor_grievance_hearing",
            )
        )
        # Dedicated fallback that stays specific to the grievance-hearing anchor.
        seed_boosted_probes.append(
            (
                "For the grievance hearing process, on what date did you request a hearing or review, how did you request it (portal/email/form/phone/in person), when did HACC respond, and what record or file verifies each step?",
                "anchor_grievance_hearing",
            )
        )
    if should_frontload_anchor_adverse_action:
        seed_boosted_probes.append(
            (
                "What exact adverse action did HACC take or threaten to take, on what date did it happen, who made or communicated it, and what notice, message, or decision record shows that action?",
                "anchor_adverse_action",
            )
        )
    if should_frontload_anchor_selection:
        seed_boosted_probes.append(
            (
                "What exact screening, selection, or evaluation criteria were used in your case, where are those criteria written, and how were they applied to you in the case file or notice?",
                "anchor_selection_criteria",
            )
        )
        # Dedicated fallback that keeps this anchor ahead of generic intake follow-ups.
        seed_boosted_probes.append(
            (
                "For selection criteria specifically, what exact factor or threshold did HACC apply to you, where is it documented, and what evidence file can verify that application?",
                "anchor_selection_criteria",
            )
        )
    if should_frontload_hearing_request_timing:
        seed_boosted_probes.append(
            (
                "When was the hearing or review requested, how was it requested, and when did HACC respond?",
                "hearing_request_timing",
            )
        )
    if should_frontload_staff_names_titles:
        seed_boosted_probes.append(
            (
                "Which HACC staff members handled each step, what were their full names and titles or roles, and how can you identify each person from the notices, emails, portal messages, or other records?",
                "staff_names_titles",
            )
        )
    if should_frontload_causation_sequence:
        seed_boosted_probes.append(
            (
                "Please walk through this step by step: protected activity, HACC response, and adverse action, including who knew each step and when.",
                "causation_sequence",
            )
        )

    if weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        seed_boosted_probes.extend(
            [
                (
                    "Which specific policy or procedure document did staff rely on, what section did they cite, and how was it applied to you?",
                    "documents",
                ),
                (
                    "Please list each supporting file you have (notice, email, text, letter, screenshot, or upload), including date, sender, and what fact it proves.",
                    "documents",
                ),
            ]
        )
    if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}):
        seed_boosted_probes.extend(
            [
                (
                    "What protected characteristic, accommodation request, or complaint came before the adverse action, and what happened right after it?",
                    "causation_sequence",
                ),
                (
                    "What exact reason was given for the housing decision, who gave it, and what date was it communicated?",
                    "adverse_action_details",
                ),
            ]
        )

    prioritized_prompts = seed_boosted_probes + cls._extract_intake_prompt_candidates(seed_complaint)
    # Keep anchor-selection probes ahead of generic catch-all prompts when unresolved.
    prompt_priority_tier: Dict[int, int] = {}
    for prompt_index, (probe_text, probe_type) in enumerate(prioritized_prompts):
        if probe_type == 'anchor_selection_criteria':
            prompt_priority_tier[prompt_index] = 0
        elif probe_type == 'anchor_adverse_action':
            prompt_priority_tier[prompt_index] = 1
        elif probe_type in {'anchor_grievance_hearing', 'anchor_appeal_rights', 'hearing_request_timing'}:
            prompt_priority_tier[prompt_index] = 1
        elif probe_type == 'staff_names_titles' and should_frontload_staff_names_titles:
            prompt_priority_tier[prompt_index] = 1
        elif probe_type == 'intake_follow_up':
            prompt_priority_tier[prompt_index] = 9
        else:
            prompt_priority_tier[prompt_index] = 3
    objective_priority: Dict[str, int] = {}
    for _, objective in prioritized_prompts:
        objective_priority.setdefault(objective, len(objective_priority))

    forced_objectives: Set[str] = set()
    if supports_selection_criteria and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        forced_objectives.update({'documents', 'anchor_selection_criteria'})
    elif weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        forced_objectives.add('documents')
    if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}):
        forced_objectives.update(
            {
                'exact_dates',
                'adverse_action_details',
                'hearing_request_timing',
                'causation_sequence',
                'anchor_adverse_action',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
            }
        )
        if supports_selection_criteria:
            forced_objectives.add('anchor_selection_criteria')
    forced_objectives.update(
        {
            objective
            for objective in (
                'anchor_adverse_action',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
                'anchor_selection_criteria',
                'hearing_request_timing',
                'staff_names_titles',
                'causation_sequence',
            )
            if objective in unresolved_intake_objectives
        }
    )
    for objective in sorted(forced_objectives):
        objective_priority.setdefault(objective, len(objective_priority))

    deduped_existing: List[Any] = []
    seen_existing: Set[str] = set()
    for question in existing_questions:
        question_text = cls._extract_question_text(question)
        key = cls._question_dedupe_key(question_text)
        if key and key in seen_existing:
            continue
        if key:
            seen_existing.add(key)
        deduped_existing.append(question)
    existing_questions = deduped_existing

    covered_objectives: Set[str] = set()
    for question in existing_questions:
        for objective in objective_priority:
            if cls._candidate_matches_intake_objective(question, objective):
                covered_objectives.add(objective)

    objective_group_coverage: Dict[str, int] = {'factual': 0, 'evidentiary': 0, 'anchor': 0}
    for objective in covered_objectives:
        group = cls._intake_objective_group(objective)
        if group in objective_group_coverage:
            objective_group_coverage[group] += 1

    group_targets = {'factual': 0, 'evidentiary': 0, 'anchor': 0}
    if not stability_recovery_mode:
        group_targets['factual'] = 3
        group_targets['evidentiary'] = 2 if weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}) else 1
        group_targets['anchor'] = 2 if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}) else 1
    elif not strict_stability_mode:
        group_targets['factual'] = 1
        group_targets['evidentiary'] = 1 if weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}) else 0
        group_targets['anchor'] = 1 if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}) else 0

    merged: List[Any] = []
    seen = set()
    skipped = set()
    injected_objectives: Set[str] = set()
    missing_objectives = [
        objective
        for objective in objective_priority
        if objective not in covered_objectives
    ]

    critical_objectives = [
        'exact_dates',
        'staff_names_titles',
        'hearing_request_timing',
        'response_dates',
        'adverse_action_details',
        'timeline',
        'actors',
        'causation_sequence',
        'documents',
        'anchor_adverse_action',
        'anchor_appeal_rights',
        'anchor_grievance_hearing',
        'anchor_selection_criteria',
        'harm_remedy',
    ]
    uncovered_critical_objectives = [
        objective for objective in critical_objectives if objective in missing_objectives
    ]

    for question in existing_questions:
        key = cls._question_dedupe_key(cls._extract_question_text(question))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(question)

    if stability_recovery_mode:
        explicit_prompt_objectives = {
            objective
            for _, objective in cls._extract_intake_prompt_candidates(seed_complaint)
        }
        missing_explicit_prompt_objectives = [
            objective
            for objective in uncovered_critical_objectives
            if objective in explicit_prompt_objectives
        ]
        if existing_questions and (
            strict_stability_mode
            or len(existing_questions) >= 2
            or not uncovered_critical_objectives
        ) and not missing_explicit_prompt_objectives:
            return merged
        # Recovery mode should prioritize continuity over aggressive backfilling.
        # Only inject a minimal, high-value probe when intake coverage is clearly weak.
        injection_budget = min(
            stability_injection_budget,
            max(1, len(uncovered_critical_objectives) or 1),
        )
        if not existing_questions:
            injection_budget = max(injection_budget, empty_questions_min_budget)
        if missing_objectives:
            injection_budget = min(injection_budget, len(missing_objectives))
    else:
        if signal_strength >= 0.75:
            injection_budget = 10
        elif signal_strength >= 0.4:
            injection_budget = 8
        else:
            injection_budget = 6
        if not existing_questions:
            injection_budget = max(injection_budget, 5)
        forced_missing = [objective for objective in forced_objectives if objective in missing_objectives]
        unmet_group_targets = sum(
            max(0, group_targets[group] - objective_group_coverage.get(group, 0))
            for group in group_targets
        )
        if forced_missing:
            injection_budget = max(injection_budget, min(12, len(forced_missing) + 4))
        if unmet_group_targets > 0:
            injection_budget = max(injection_budget, min(12, unmet_group_targets + 4))

    weighted_prompts: List[tuple[int, float, int, str, str]] = []
    for index, (probe_text, probe_type) in enumerate(prioritized_prompts):
        weight = cls._intake_objective_weight(probe_type, optimizer_context)
        if probe_type in forced_objectives:
            weight += 0.75
        if probe_type == 'anchor_selection_criteria' and should_frontload_anchor_selection:
            weight += 0.95
        if probe_type == 'anchor_adverse_action' and should_frontload_anchor_adverse_action:
            weight += 0.93
        if probe_type == 'anchor_appeal_rights' and should_frontload_anchor_appeal_rights:
            weight += 0.90
        if probe_type == 'anchor_grievance_hearing' and should_frontload_anchor_grievance_hearing:
            weight += 0.90
        if probe_type == 'hearing_request_timing' and should_frontload_hearing_request_timing:
            weight += 0.88
        if probe_type == 'staff_names_titles' and should_frontload_staff_names_titles:
            weight += 0.92
        if probe_type == 'causation_sequence' and should_frontload_causation_sequence:
            weight += 0.75
        if probe_type == 'intake_follow_up':
            # Keep generic catch-all prompts behind unresolved anchor/timing objectives.
            weight -= 0.40
            if (
                should_frontload_anchor_grievance_hearing
                or should_frontload_anchor_adverse_action
                or should_frontload_anchor_selection
                or 'anchor_grievance_hearing' in unresolved_intake_objectives
                or 'anchor_adverse_action' in unresolved_intake_objectives
                or 'anchor_selection_criteria' in unresolved_intake_objectives
            ):
                weight -= 0.75
        group = cls._intake_objective_group(probe_type)
        if group in group_targets:
            remaining = max(0, group_targets[group] - objective_group_coverage.get(group, 0))
            if remaining > 0:
                weight += min(0.9, remaining * 0.35)
        if probe_type in missing_objectives:
            weight += 0.25
        tier = prompt_priority_tier.get(index, 3)
        if probe_type == 'anchor_selection_criteria' and should_frontload_anchor_selection:
            tier = 0
        if probe_type == 'intake_follow_up':
            tier = max(tier, 9)
        weighted_prompts.append((tier, weight, index, probe_text, probe_type))
    weighted_prompts.sort(key=lambda item: (item[0], -item[1], item[2]))

    injected = 0
    injected_questions: List[Any] = []
    injected_objective_counts: Dict[str, int] = {}
    max_per_objective: Dict[str, int] = {}
    if (
        not stability_recovery_mode
        and should_frontload_anchor_selection
        and 'anchor_selection_criteria' in missing_objectives
    ):
        # Allow one dedicated fallback on top of the primary selection-criteria probe.
        max_per_objective['anchor_selection_criteria'] = 2
    strict_recovery_objectives = {
        'timeline',
        'actors',
        'adverse_action_details',
        'documents',
        'hearing_request_timing',
        'response_dates',
        'anchor_adverse_action',
        'anchor_appeal_rights',
        'anchor_grievance_hearing',
        'anchor_selection_criteria',
        'causation_sequence',
        'harm_remedy',
        'exact_dates',
        'staff_names_titles',
    }
    for _tier, _weight, _index, probe_text, probe_type in weighted_prompts:
        if injected >= injection_budget:
            break
        current_count = injected_objective_counts.get(probe_type, 0)
        per_objective_limit = max_per_objective.get(probe_type, 1)
        if stability_recovery_mode and one_probe_per_objective_in_stability:
            per_objective_limit = 1
        if current_count >= per_objective_limit:
            continue
        if (
            stability_recovery_mode
            and limit_to_missing_objectives_in_stability
            and missing_objectives
            and probe_type not in missing_objectives
        ):
            continue
        if not stability_recovery_mode and missing_objectives and probe_type not in missing_objectives:
            continue
        if stability_recovery_mode and probe_type not in critical_objectives and missing_objectives:
            continue
        if strict_stability_mode and probe_type not in strict_recovery_objectives and missing_objectives:
            continue
        key = cls._question_dedupe_key(probe_text)
        if key and (key in seen or key in skipped):
            continue
        evidence_anchor = cls._strongest_evidence_anchor_for_objective(
            probe_type,
            weak_evidence_modalities,
        )
        tightened_probe_text = probe_text
        if (
            probe_type in unresolved_intake_objectives
            or probe_type in forced_objectives
            or probe_type in {'anchor_grievance_hearing', 'anchor_selection_criteria'}
        ):
            tightened_probe_text = cls._tighten_intake_question_text(
                probe_text,
                probe_type,
                evidence_anchor,
            )
        synthetic_question = {
            "question": tightened_probe_text,
            "type": probe_type,
            "question_objective": probe_type,
            "question_reason": "Structured intake prompt imported from the grounding bundle.",
            "source": "synthetic_intake_prompt",
        }
        if any(
            cls._questions_substantially_overlap(synthetic_question, existing_question)
            for existing_question in existing_questions
        ):
            if key:
                skipped.add(key)
            continue
        if key and key not in seen:
            seen.add(key)
            injected_objectives.add(probe_type)
            injected_objective_counts[probe_type] = injected_objective_counts.get(probe_type, 0) + 1
            injected_questions.append(synthetic_question)
            objective_group = cls._intake_objective_group(probe_type)
            if objective_group in objective_group_coverage:
                objective_group_coverage[objective_group] += 1
            injected += 1

    # Final guardrail for non-recovery runs: if weak areas are still uncovered and
    # budget remains, add one extra high-priority question per unmet objective group.
    if not stability_recovery_mode and injected < injection_budget:
        unmet_groups = [
            group
            for group, target_count in group_targets.items()
            if objective_group_coverage.get(group, 0) < target_count
        ]
        for group in unmet_groups:
            if injected >= injection_budget:
                break
            for _tier, _weight, _index, probe_text, probe_type in weighted_prompts:
                if cls._intake_objective_group(probe_type) != group:
                    continue
                current_count = injected_objective_counts.get(probe_type, 0)
                per_objective_limit = max_per_objective.get(probe_type, 1)
                key = cls._question_dedupe_key(probe_text)
                if current_count >= per_objective_limit:
                    continue
                if key and (key in seen or key in skipped):
                    continue
                evidence_anchor = cls._strongest_evidence_anchor_for_objective(
                    probe_type,
                    weak_evidence_modalities,
                )
                tightened_probe_text = cls._tighten_intake_question_text(
                    probe_text,
                    probe_type,
                    evidence_anchor,
                )
                synthetic_question = {
                    "question": tightened_probe_text,
                    "type": probe_type,
                    "question_objective": probe_type,
                    "question_reason": "Structured intake prompt imported from the grounding bundle.",
                    "source": "synthetic_intake_prompt",
                }
                if any(
                    cls._questions_substantially_overlap(synthetic_question, existing_question)
                    for existing_question in existing_questions
                ):
                    if key:
                        skipped.add(key)
                    continue
                if key:
                    seen.add(key)
                injected_objectives.add(probe_type)
                injected_objective_counts[probe_type] = injected_objective_counts.get(probe_type, 0) + 1
                injected_questions.append(synthetic_question)
                objective_group_coverage[group] = objective_group_coverage.get(group, 0) + 1
                injected += 1
                break

    if stability_recovery_mode:
        # Recovery budgets stay intentionally small; when we do inject a probe,
        # put it ahead of generic existing questions so unresolved anchor and
        # chronology objectives are actually surfaced first.
        return injected_questions + merged
    return injected_questions + merged


def _reprioritize_candidates_for_intake_objectives(
    cls,
    candidates: Sequence[Any],
    seed_complaint: Dict[str, Any],
    *,
    max_questions: int,
) -> List[Any]:
    intake_candidates = cls._extract_intake_prompt_candidates(seed_complaint)
    if not intake_candidates:
        return list(candidates or [])[:max_questions]

    optimizer_context = cls._extract_actor_critic_intake_context(seed_complaint)
    key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
    unresolved_intake_objectives: Set[str] = set()
    chronology_priority_hints = cls._extract_document_chronology_priority_hints(seed_complaint)
    unresolved_objective_keys = ('unresolved_intake_objectives', 'uncovered_objectives', 'focus_areas')
    context_payloads = [
        seed_complaint,
        key_facts,
        seed_complaint.get('_meta') if isinstance(seed_complaint.get('_meta'), dict) else None,
        seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint.get('actor_critic_optimizer'), dict) else None,
        seed_complaint.get('optimization_guidance') if isinstance(seed_complaint.get('optimization_guidance'), dict) else None,
        seed_complaint.get('document_optimization') if isinstance(seed_complaint.get('document_optimization'), dict) else None,
    ]
    for payload in context_payloads:
        if not isinstance(payload, dict):
            continue
        nested_payloads = [
            payload,
            payload.get('intake_priorities') if isinstance(payload.get('intake_priorities'), dict) else None,
            payload.get('document_handoff_summary') if isinstance(payload.get('document_handoff_summary'), dict) else None,
        ]
        for nested in nested_payloads:
            if not isinstance(nested, dict):
                continue
            for key in unresolved_objective_keys:
                for value in list(nested.get(key) or []):
                    objective = str(value or '').strip().lower()
                    if objective:
                        unresolved_intake_objectives.add(objective)
    unresolved_intake_objectives.update(
        str(value).strip().lower()
        for value in list(chronology_priority_hints.get('objectives') or [])
        if str(value).strip()
    )
    signal_values = [
        float(value)
        for value in (
            optimizer_context.get('question_quality'),
            optimizer_context.get('empathy'),
            optimizer_context.get('efficiency'),
        )
        if isinstance(value, (int, float))
    ]
    stability_recovery_mode = (not signal_values) or max(signal_values) <= 0.05
    objective_priority: Dict[str, int] = {}
    for _, objective in intake_candidates:
        objective_priority.setdefault(objective, len(objective_priority))

    forced_objectives: Set[str] = set()
    weak_evidence_modalities = set(optimizer_context.get('weak_evidence_modalities') or set())
    weak_complaint_types = set(optimizer_context.get('weak_complaint_types') or set())
    supports_selection_criteria = cls._seed_supports_selection_criteria(seed_complaint)
    should_frontload_anchor_selection = bool(
        (
            supports_selection_criteria
            and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'})
        )
        or 'anchor_selection_criteria' in unresolved_intake_objectives
    )
    should_frontload_anchor_appeal_rights = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_appeal_rights' in unresolved_intake_objectives
    )
    should_frontload_anchor_grievance_hearing = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_grievance_hearing' in unresolved_intake_objectives
    )
    should_frontload_anchor_adverse_action = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_adverse_action' in unresolved_intake_objectives
        or 'adverse_action' in cls._extract_anchor_sections(seed_complaint)
    )
    should_frontload_hearing_request_timing = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'hearing_request_timing' in unresolved_intake_objectives
        or 'anchor_grievance_hearing' in unresolved_intake_objectives
    )
    should_frontload_staff_names_titles = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'staff_names_titles' in unresolved_intake_objectives
        or bool(cls._extract_anchor_sections(seed_complaint).intersection({'grievance_hearing', 'appeal_rights', 'adverse_action'}))
    )
    should_frontload_causation_sequence = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'causation_sequence' in unresolved_intake_objectives
        or bool(chronology_priority_hints.get('needs_chronology_closure'))
    )
    if supports_selection_criteria and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        forced_objectives.update({'documents', 'anchor_selection_criteria'})
    elif weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        forced_objectives.add('documents')
    if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}):
        forced_objectives.update(
            {
                'exact_dates',
                'adverse_action_details',
                'hearing_request_timing',
                'causation_sequence',
                'anchor_adverse_action',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
            }
        )
        if supports_selection_criteria:
            forced_objectives.add('anchor_selection_criteria')
    forced_objectives.update(
        {
            objective
            for objective in (
                'anchor_adverse_action',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
                'anchor_selection_criteria',
                'hearing_request_timing',
                'staff_names_titles',
                'causation_sequence',
            )
            if objective in unresolved_intake_objectives
        }
    )
    if should_frontload_staff_names_titles:
        forced_objectives.add('staff_names_titles')
    if should_frontload_anchor_adverse_action:
        forced_objectives.add('anchor_adverse_action')
    if bool(chronology_priority_hints.get('needs_chronology_closure')):
        forced_objectives.update({'timeline', 'exact_dates'})
    if bool(chronology_priority_hints.get('needs_decision_document_precision')):
        forced_objectives.add('documents')
    for objective in sorted(forced_objectives):
        objective_priority.setdefault(objective, len(objective_priority))
    if should_frontload_anchor_adverse_action and 'anchor_adverse_action' in objective_priority:
        objective_priority['anchor_adverse_action'] = min(-6, objective_priority['anchor_adverse_action'])
    if should_frontload_anchor_appeal_rights and 'anchor_appeal_rights' in objective_priority:
        objective_priority['anchor_appeal_rights'] = min(-5, objective_priority['anchor_appeal_rights'])
    if should_frontload_anchor_grievance_hearing and 'anchor_grievance_hearing' in objective_priority:
        objective_priority['anchor_grievance_hearing'] = min(-6, objective_priority['anchor_grievance_hearing'])
    if should_frontload_anchor_selection and 'anchor_selection_criteria' in objective_priority:
        objective_priority['anchor_selection_criteria'] = min(-7, objective_priority['anchor_selection_criteria'])
    if should_frontload_hearing_request_timing and 'hearing_request_timing' in objective_priority:
        objective_priority['hearing_request_timing'] = min(-3, objective_priority['hearing_request_timing'])
    if should_frontload_staff_names_titles and 'staff_names_titles' in objective_priority:
        objective_priority['staff_names_titles'] = min(-4, objective_priority['staff_names_titles'])
    if should_frontload_causation_sequence and 'causation_sequence' in objective_priority:
        objective_priority['causation_sequence'] = min(-2, objective_priority['causation_sequence'])
    if bool(chronology_priority_hints.get('needs_chronology_closure')) and 'timeline' in objective_priority:
        objective_priority['timeline'] = min(-8, objective_priority['timeline'])
    if bool(chronology_priority_hints.get('needs_chronology_closure')) and 'exact_dates' in objective_priority:
        objective_priority['exact_dates'] = min(-7, objective_priority['exact_dates'])
    if bool(chronology_priority_hints.get('needs_chronology_closure')) and 'causation_sequence' in objective_priority:
        objective_priority['causation_sequence'] = min(-6, objective_priority['causation_sequence'])
    if bool(chronology_priority_hints.get('needs_decision_document_precision')) and 'documents' in objective_priority:
        objective_priority['documents'] = min(-3, objective_priority['documents'])
    if bool(chronology_priority_hints.get('needs_exhibit_grounding')) and 'documents' in objective_priority:
        objective_priority['documents'] = min(-5, objective_priority['documents'])

    for objective in list(objective_priority):
        if objective == 'documents' and set(optimizer_context.get('weak_evidence_modalities') or set()).intersection({'policy_document', 'file_evidence'}):
            objective_priority[objective] = max(-6, objective_priority[objective] - 3)
        if objective.startswith('anchor_') and (
            optimizer_context.get('is_housing_discrimination') or optimizer_context.get('is_hacc_research_seed')
        ):
            objective_priority[objective] = max(-6, objective_priority[objective] - 1)
        if objective in forced_objectives:
            objective_priority[objective] = max(-6, objective_priority[objective] - 2)
        if objective in unresolved_intake_objectives:
            objective_priority[objective] = max(-6, objective_priority[objective] - 2)
        if objective == 'intake_follow_up' and (
            should_frontload_anchor_adverse_action
            or should_frontload_anchor_grievance_hearing
            or should_frontload_anchor_selection
            or should_frontload_hearing_request_timing
            or 'anchor_adverse_action' in unresolved_intake_objectives
            or 'anchor_grievance_hearing' in unresolved_intake_objectives
            or 'anchor_selection_criteria' in unresolved_intake_objectives
        ):
            objective_priority[objective] = min(99, objective_priority[objective] + 12)

    ranked: List[tuple[tuple[Any, ...], Any, List[str]]] = []
    for index, candidate in enumerate(list(candidates or [])):
        best_priority = float(len(objective_priority) + 1)
        matched_objectives: List[str] = []
        for objective, priority in objective_priority.items():
            if cls._candidate_matches_intake_objective(candidate, objective):
                matched_objectives.append(objective)
                objective_weight = cls._intake_objective_weight(objective, optimizer_context)
                if objective in forced_objectives:
                    objective_weight += 0.7
                if objective in unresolved_intake_objectives:
                    objective_weight += 0.55
                boost_scale = 0.2 if stability_recovery_mode else 0.5
                weighted_priority = max(0.0, float(priority) - min(0.8, (objective_weight - 1.0) * boost_scale))
                if weighted_priority < best_priority:
                    best_priority = weighted_priority
        selector_score = 0.0
        if isinstance(candidate, dict):
            selector_score = float(candidate.get('selector_score', 0.0) or 0.0)
        proof_priority = 99
        if isinstance(candidate, dict):
            proof_priority = int(candidate.get('proof_priority', 99) or 99)
        phase_focus_rank = cls._phase_focus_rank_for_candidate(candidate)
        actor_critic_score = cls._extract_actor_critic_score(candidate)
        actor_critic_normalized = cls._normalized_actor_critic_score(candidate)
        selector_score_normalized = cls._normalized_selector_score(candidate)
        question_text = cls._extract_question_text(candidate)
        quality_score = cls._question_quality_score(candidate, question_text)
        unresolved_anchor_alignment = 0.0
        unresolved_specificity = 0.0
        if matched_objectives:
            unresolved_ranked = sorted(
                [objective for objective in matched_objectives if objective in unresolved_intake_objectives],
                key=lambda item: objective_priority.get(item, 999),
            )
            if unresolved_ranked:
                unresolved_target = unresolved_ranked[0]
                mentions_anchor = cls._question_mentions_evidence_anchor(question_text, unresolved_target)
                unresolved_anchor_alignment = 0.35 if mentions_anchor else -0.18
                precision = cls._question_precision_score(question_text)
                unresolved_specificity = 0.22 if precision >= 0.35 else -0.12
                adjusted_priority = best_priority - unresolved_anchor_alignment - unresolved_specificity
                best_priority = max(0.0, adjusted_priority)
        blocker_match_count = 0
        for objective in matched_objectives:
            if objective in {
                'exact_dates',
                'staff_names_titles',
                'hearing_request_timing',
                'response_dates',
                'causation_sequence',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
                'anchor_selection_criteria',
            }:
                blocker_match_count += 1
        objective_weight_sum = sum(
            cls._intake_objective_weight(objective, optimizer_context)
            for objective in matched_objectives
        )
        forced_objective_matches = sum(
            1 for objective in matched_objectives if objective in forced_objectives
        )
        group_priority = min(
            (
                {
                    'anchor': 0,
                    'evidentiary': 1,
                    'factual': 2,
                    'other': 3,
                }.get(cls._intake_objective_group(objective), 3)
                for objective in matched_objectives
            ),
            default=3,
        )

        annotated_candidate = candidate
        if isinstance(candidate, dict):
            annotated_candidate = dict(candidate)
            annotated_priority_match = matched_objectives[:1] if matched_objectives else []
            explanation = dict(
                annotated_candidate.get('ranking_explanation', {})
                if isinstance(annotated_candidate.get('ranking_explanation'), dict)
                else {}
            )
            selector_signals = dict(
                annotated_candidate.get('selector_signals', {})
                if isinstance(annotated_candidate.get('selector_signals'), dict)
                else {}
            )
            selector_signals['intake_priority_match'] = annotated_priority_match
            selector_signals['intake_priority_rank'] = None if not matched_objectives else best_priority
            selector_signals['phase_focus_rank'] = phase_focus_rank
            selector_signals['actor_critic_score'] = actor_critic_score
            selector_signals['actor_critic_score_normalized'] = actor_critic_normalized
            selector_signals['selector_score_normalized'] = selector_score_normalized
            selector_signals['blocker_match_count'] = blocker_match_count
            selector_signals['intake_objective_weighted_score'] = objective_weight_sum
            selector_signals['forced_objective_matches'] = forced_objective_matches
            selector_signals['intake_group_priority'] = group_priority
            selector_signals['question_quality_score'] = quality_score
            selector_signals['unresolved_anchor_alignment'] = unresolved_anchor_alignment
            selector_signals['unresolved_specificity'] = unresolved_specificity
            annotated_candidate['selector_signals'] = selector_signals
            explanation['intake_priority_match'] = annotated_priority_match
            explanation['intake_priority_rank'] = None if not matched_objectives else best_priority
            explanation['phase_focus_rank'] = phase_focus_rank
            explanation['actor_critic_score'] = actor_critic_score
            explanation['actor_critic_score_normalized'] = actor_critic_normalized
            explanation['selector_score_normalized'] = selector_score_normalized
            explanation['blocker_match_count'] = blocker_match_count
            explanation['intake_objective_weighted_score'] = objective_weight_sum
            explanation['forced_objective_matches'] = forced_objective_matches
            explanation['intake_group_priority'] = group_priority
            explanation['question_quality_score'] = quality_score
            explanation['unresolved_anchor_alignment'] = unresolved_anchor_alignment
            explanation['unresolved_specificity'] = unresolved_specificity
            annotated_candidate['ranking_explanation'] = explanation

        ranked.append(
            (
                (
                    best_priority,
                    group_priority if not stability_recovery_mode else phase_focus_rank,
                    -forced_objective_matches if not stability_recovery_mode else index,
                    # During low-signal recovery, keep ordering stable and avoid
                    # over-reacting to weak actor-critic gradients.
                    index if stability_recovery_mode else phase_focus_rank,
                    phase_focus_rank if stability_recovery_mode else -blocker_match_count,
                    -blocker_match_count if stability_recovery_mode else -objective_weight_sum,
                    -objective_weight_sum if stability_recovery_mode else -quality_score,
                    -quality_score if stability_recovery_mode else -actor_critic_normalized,
                    -selector_score_normalized if stability_recovery_mode else -selector_score_normalized,
                    -selector_score if stability_recovery_mode else -selector_score,
                    proof_priority if stability_recovery_mode else -actor_critic_score,
                    -actor_critic_score if stability_recovery_mode else proof_priority,
                    index,
                ),
                annotated_candidate,
                matched_objectives,
            )
        )

    ranked.sort(key=lambda item: item[0])
    ranked_candidates = [candidate for _, candidate, _ in ranked]
    ranked_objectives = [matched_objectives for _, _, matched_objectives in ranked]

    if stability_recovery_mode:
        # Preserve mediator ordering during recovery and avoid aggressive
        # objective-forcing while signals are uninformative.
        selected: List[Any] = []
        if bool(chronology_priority_hints.get('needs_chronology_closure')):
            for chronology_objective in ('timeline', 'exact_dates', 'causation_sequence'):
                added = False
                for rank_index, candidate in enumerate(ranked_candidates):
                    matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
                    if chronology_objective not in matched:
                        continue
                    if any(cls._questions_substantially_overlap(candidate, existing) for existing in selected):
                        continue
                    unresolved_ranked = sorted(
                        [objective for objective in matched if objective in unresolved_intake_objectives],
                        key=lambda item: objective_priority.get(item, 999),
                    )
                    tightened_candidate = candidate
                    for objective in unresolved_ranked:
                        if cls._intake_objective_group(objective) not in {'factual', 'anchor'}:
                            continue
                        evidence_anchor = cls._strongest_evidence_anchor_for_objective(
                            objective,
                            weak_evidence_modalities,
                        )
                        tightened_candidate = cls._tighten_intake_candidate_for_objective(
                            candidate,
                            objective,
                            evidence_anchor,
                        )
                        break
                    selected.append(tightened_candidate)
                    added = True
                    break
                if added or len(selected) >= max_questions:
                    break
        for rank_index, candidate in enumerate(ranked_candidates):
            if len(selected) >= max_questions:
                break
            if any(cls._questions_substantially_overlap(candidate, existing) for existing in selected):
                continue
            matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
            unresolved_ranked = sorted(
                [objective for objective in matched if objective in unresolved_intake_objectives],
                key=lambda item: objective_priority.get(item, 999),
            )
            tightened_candidate = candidate
            for objective in unresolved_ranked:
                if cls._intake_objective_group(objective) not in {'factual', 'anchor'}:
                    continue
                evidence_anchor = cls._strongest_evidence_anchor_for_objective(
                    objective,
                    weak_evidence_modalities,
                )
                tightened_candidate = cls._tighten_intake_candidate_for_objective(
                    candidate,
                    objective,
                    evidence_anchor,
                )
                break
            selected.append(tightened_candidate)
        return selected[:max_questions]

    selected: List[Any] = []
    selected_objectives: Set[str] = set()
    selected_indexes: Set[int] = set()
    selected_group_counts: Dict[str, int] = {'factual': 0, 'evidentiary': 0, 'anchor': 0}
    group_targets = {'factual': 1, 'evidentiary': 0, 'anchor': 0}
    if weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        group_targets['evidentiary'] = 1
    if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}):
        group_targets['anchor'] = 1
        group_targets['factual'] = 2
    if (
        should_frontload_anchor_adverse_action
        or should_frontload_anchor_appeal_rights
        or should_frontload_anchor_grievance_hearing
    ):
        group_targets['anchor'] = max(group_targets['anchor'], 2)

    def tighten_selected_candidate(candidate: Any, matched: List[str]) -> Any:
        unresolved_ranked = sorted(
            [objective for objective in matched if objective in unresolved_intake_objectives],
            key=lambda item: objective_priority.get(item, 999),
        )
        unresolved_priority_order = [
            'anchor_selection_criteria',
            'anchor_grievance_hearing',
            'anchor_adverse_action',
            'hearing_request_timing',
            'staff_names_titles',
            'causation_sequence',
            'adverse_action_details',
            'exact_dates',
            'response_dates',
            'staff_names_titles',
            'documents',
        ]
        unresolved_ranked = sorted(
            unresolved_ranked,
            key=lambda item: (
                unresolved_priority_order.index(item)
                if item in unresolved_priority_order
                else len(unresolved_priority_order),
                objective_priority.get(item, 999),
            ),
        )
        for objective in unresolved_ranked:
            if cls._intake_objective_group(objective) not in {'factual', 'anchor'}:
                continue
            evidence_anchor = cls._strongest_evidence_anchor_for_objective(
                objective,
                weak_evidence_modalities,
            )
            tightened = cls._tighten_intake_candidate_for_objective(candidate, objective, evidence_anchor)
            if not isinstance(tightened, dict):
                return tightened
            question_text = cls._extract_question_text(tightened)
            objective_specific_suffix = {
                'anchor_selection_criteria': " Please ask for the exact criterion/threshold, where it appears in policy, and the matching case-file or notice citation.",
                'anchor_grievance_hearing': " Keep this question limited to request date, method, response date, and the record that verifies each step.",
                'anchor_adverse_action': " Keep this question limited to the exact adverse action, the action date, who communicated it, and the notice or record that proves it.",
                'hearing_request_timing': " Ask for exact request/response dates and the record that proves each date.",
                'causation_sequence': " Tie the sequence to dated records for each event.",
                'adverse_action_details': " Require who made the decision, the stated reason, communication channel, and exact date.",
                'exact_dates': " Request exact dates (not rough ranges) with matching records.",
                'response_dates': " Require the response date, sender, and source record.",
                'staff_names_titles': " Ask for full name, title, and how they were identified in records.",
            }.get(objective, "")
            if objective_specific_suffix and objective_specific_suffix.strip() not in question_text:
                updated = dict(tightened)
                updated['question'] = f"{question_text}{objective_specific_suffix}"
                selector_signals = dict(
                    updated.get('selector_signals', {})
                    if isinstance(updated.get('selector_signals'), dict)
                    else {}
                )
                selector_signals['tightened_specific_gap'] = objective
                updated['selector_signals'] = selector_signals
                explanation = dict(
                    updated.get('ranking_explanation', {})
                    if isinstance(updated.get('ranking_explanation'), dict)
                    else {}
                )
                explanation['tightened_specific_gap'] = objective
                updated['ranking_explanation'] = explanation
                return updated
            return tightened
        return candidate

    if bool(chronology_priority_hints.get('needs_chronology_closure')):
        for chronology_objective in ('timeline', 'exact_dates', 'causation_sequence'):
            added = False
            for rank_index, candidate in enumerate(ranked_candidates):
                if rank_index in selected_indexes:
                    continue
                matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
                if chronology_objective not in matched:
                    continue
                if any(cls._questions_substantially_overlap(candidate, existing) for existing in selected):
                    continue
                selected.append(tighten_selected_candidate(candidate, matched))
                selected_indexes.add(rank_index)
                selected_objectives.update(matched)
                for matched_objective in matched:
                    group = cls._intake_objective_group(matched_objective)
                    if group in selected_group_counts:
                        selected_group_counts[group] += 1
                added = True
                break
            if added or len(selected) >= max_questions:
                break
        if len(selected) >= max_questions:
            return selected

    for objective in sorted(forced_objectives, key=lambda item: objective_priority.get(item, 99)):
        for rank_index, candidate in enumerate(ranked_candidates):
            if rank_index in selected_indexes:
                continue
            matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
            if objective not in matched:
                continue
            if any(cls._questions_substantially_overlap(candidate, existing) for existing in selected):
                continue
            selected.append(tighten_selected_candidate(candidate, matched))
            selected_indexes.add(rank_index)
            selected_objectives.update(matched)
            for matched_objective in matched:
                group = cls._intake_objective_group(matched_objective)
                if group in selected_group_counts:
                    selected_group_counts[group] += 1
            if len(selected) >= max_questions:
                return selected
            break

    for group, target_count in group_targets.items():
        while selected_group_counts.get(group, 0) < target_count and len(selected) < max_questions:
            added = False
            for rank_index, candidate in enumerate(ranked_candidates):
                if rank_index in selected_indexes:
                    continue
                matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
                if not any(cls._intake_objective_group(objective) == group for objective in matched):
                    continue
                if any(cls._questions_substantially_overlap(candidate, existing) for existing in selected):
                    continue
                selected.append(tighten_selected_candidate(candidate, matched))
                selected_indexes.add(rank_index)
                selected_objectives.update(matched)
                for matched_objective in matched:
                    matched_group = cls._intake_objective_group(matched_objective)
                    if matched_group in selected_group_counts:
                        selected_group_counts[matched_group] += 1
                added = True
                if len(selected) >= max_questions:
                    return selected
                break
            if not added:
                break

    for objective, _priority in sorted(objective_priority.items(), key=lambda item: item[1]):
        for rank_index, candidate in enumerate(ranked_candidates):
            if rank_index in selected_indexes:
                continue
            matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
            if objective not in matched:
                continue
            if any(cls._questions_substantially_overlap(candidate, existing) for existing in selected):
                continue
            selected.append(tighten_selected_candidate(candidate, matched))
            selected_indexes.add(rank_index)
            selected_objectives.update(matched)
            for matched_objective in matched:
                group = cls._intake_objective_group(matched_objective)
                if group in selected_group_counts:
                    selected_group_counts[group] += 1
            if len(selected) >= max_questions:
                return selected
            break

    for rank_index, candidate in enumerate(ranked_candidates):
        if len(selected) >= max_questions:
            break
        if rank_index in selected_indexes:
            continue
        matched = ranked_objectives[rank_index] if rank_index < len(ranked_objectives) else []
        adds_new_coverage = any(objective not in selected_objectives for objective in matched)
        if not adds_new_coverage and any(
            cls._questions_substantially_overlap(candidate, existing) for existing in selected
        ):
            continue
        selected.append(tighten_selected_candidate(candidate, matched))
        selected_indexes.add(rank_index)
        selected_objectives.update(matched)
        for matched_objective in matched:
            group = cls._intake_objective_group(matched_objective)
            if group in selected_group_counts:
                selected_group_counts[group] += 1

    return selected[:max_questions]


def _summarize_intake_priority_coverage(
    cls,
    questions: Sequence[Any],
    seed_complaint: Dict[str, Any],
) -> Dict[str, Any]:
    intake_candidates = cls._extract_intake_prompt_candidates(seed_complaint)
    optimizer_context = cls._extract_actor_critic_intake_context(seed_complaint)
    key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
    unresolved_intake_objectives: Set[str] = set()
    unresolved_objective_keys = ('unresolved_intake_objectives', 'uncovered_objectives', 'focus_areas')
    context_payloads = [
        seed_complaint,
        key_facts,
        seed_complaint.get('_meta') if isinstance(seed_complaint.get('_meta'), dict) else None,
        seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint.get('actor_critic_optimizer'), dict) else None,
        seed_complaint.get('optimization_guidance') if isinstance(seed_complaint.get('optimization_guidance'), dict) else None,
        seed_complaint.get('document_optimization') if isinstance(seed_complaint.get('document_optimization'), dict) else None,
    ]
    for payload in context_payloads:
        if not isinstance(payload, dict):
            continue
        nested_payloads = [
            payload,
            payload.get('intake_priorities') if isinstance(payload.get('intake_priorities'), dict) else None,
            payload.get('document_handoff_summary') if isinstance(payload.get('document_handoff_summary'), dict) else None,
        ]
        for nested in nested_payloads:
            if not isinstance(nested, dict):
                continue
            for key in unresolved_objective_keys:
                for value in list(nested.get(key) or []):
                    objective = str(value or '').strip().lower()
                    if objective:
                        unresolved_intake_objectives.add(objective)
    signal_values = [
        float(value)
        for value in (
            optimizer_context.get('question_quality'),
            optimizer_context.get('empathy'),
            optimizer_context.get('efficiency'),
        )
        if isinstance(value, (int, float))
    ]
    stability_recovery_mode = (not signal_values) or max(signal_values) <= 0.05
    expected_objectives: List[str] = []
    for _, objective in intake_candidates:
        if objective not in expected_objectives:
            expected_objectives.append(objective)

    weak_complaint_types = set(optimizer_context.get('weak_complaint_types') or set())
    weak_evidence_modalities = set(optimizer_context.get('weak_evidence_modalities') or set())
    supports_selection_criteria = cls._seed_supports_selection_criteria(seed_complaint)
    should_frontload_anchor_selection = bool(
        (
            supports_selection_criteria
            and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'})
        )
        or 'anchor_selection_criteria' in unresolved_intake_objectives
    )
    should_frontload_anchor_appeal_rights = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_appeal_rights' in unresolved_intake_objectives
    )
    should_frontload_anchor_grievance_hearing = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_grievance_hearing' in unresolved_intake_objectives
    )
    should_frontload_anchor_adverse_action = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'anchor_adverse_action' in unresolved_intake_objectives
        or 'adverse_action' in cls._extract_anchor_sections(seed_complaint)
    )
    should_frontload_hearing_request_timing = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'hearing_request_timing' in unresolved_intake_objectives
        or 'anchor_grievance_hearing' in unresolved_intake_objectives
    )
    should_frontload_staff_names_titles = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'staff_names_titles' in unresolved_intake_objectives
        or bool(cls._extract_anchor_sections(seed_complaint).intersection({'grievance_hearing', 'appeal_rights', 'adverse_action'}))
    )
    should_frontload_causation_sequence = bool(
        weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'})
        or 'causation_sequence' in unresolved_intake_objectives
    )
    forced_objectives: Set[str] = set()
    if supports_selection_criteria and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        forced_objectives.update({'documents', 'anchor_selection_criteria'})
    elif weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        forced_objectives.add('documents')
    if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}):
        forced_objectives.update(
            {
                'exact_dates',
                'adverse_action_details',
                'hearing_request_timing',
                'causation_sequence',
                'anchor_adverse_action',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
            }
        )
        if supports_selection_criteria:
            forced_objectives.add('anchor_selection_criteria')
    forced_objectives.update(
        {
            objective
            for objective in (
                'anchor_adverse_action',
                'anchor_appeal_rights',
                'anchor_grievance_hearing',
                'anchor_selection_criteria',
                'hearing_request_timing',
                'staff_names_titles',
                'causation_sequence',
            )
            if objective in unresolved_intake_objectives
        }
    )
    if should_frontload_staff_names_titles:
        forced_objectives.add('staff_names_titles')
    if should_frontload_anchor_adverse_action:
        forced_objectives.add('anchor_adverse_action')
    for objective in sorted(forced_objectives):
        if objective not in expected_objectives:
            expected_objectives.append(objective)

    # Keep unresolved anchor objectives ahead of generic catch-all prompts.
    def _objective_sort_key(item: str) -> tuple[int, int]:
        if item == 'anchor_selection_criteria':
            return (0, 0)
        if item == 'anchor_grievance_hearing':
            return (0, 1)
        if item == 'intake_follow_up':
            return (9, 9)
        return (1, expected_objectives.index(item))

    expected_objectives = sorted(dict.fromkeys(expected_objectives), key=_objective_sort_key)

    # When an anchor-specific adverse-action objective is present, treat it as the
    # preferred intake target unless factual adverse-action detail coverage is explicitly forced.
    if (
        'anchor_adverse_action' in expected_objectives
        and 'adverse_action_details' in expected_objectives
        and 'adverse_action_details' not in forced_objectives
    ):
        expected_objectives = [
            objective for objective in expected_objectives if objective != 'adverse_action_details'
        ]

    if (
        set(optimizer_context.get('weak_evidence_modalities') or set()).intersection({'policy_document', 'file_evidence'})
        and 'documents' not in expected_objectives
    ):
        expected_objectives.append('documents')

    coverage_counts: Dict[str, int] = {}
    for objective in expected_objectives:
        coverage_counts[objective] = 0

    for question in list(questions or []):
        for objective in expected_objectives:
            if cls._candidate_matches_intake_objective(question, objective):
                coverage_counts[objective] = coverage_counts.get(objective, 0) + 1

    covered_objectives = [
        objective for objective in expected_objectives if coverage_counts.get(objective, 0) > 0
    ]
    uncovered_objectives = [
        objective for objective in expected_objectives if coverage_counts.get(objective, 0) <= 0
    ]

    grouped_expected: Dict[str, List[str]] = {'factual': [], 'evidentiary': [], 'anchor': [], 'other': []}
    grouped_covered: Dict[str, List[str]] = {'factual': [], 'evidentiary': [], 'anchor': [], 'other': []}
    grouped_uncovered: Dict[str, List[str]] = {'factual': [], 'evidentiary': [], 'anchor': [], 'other': []}
    for objective in expected_objectives:
        group = cls._intake_objective_group(objective)
        grouped_expected.setdefault(group, []).append(objective)
        if objective in covered_objectives:
            grouped_covered.setdefault(group, []).append(objective)
        else:
            grouped_uncovered.setdefault(group, []).append(objective)

    group_coverage_rates: Dict[str, float] = {}
    for group in grouped_expected:
        expected_count = len(grouped_expected.get(group, []))
        covered_count = len(grouped_covered.get(group, []))
        group_coverage_rates[group] = 1.0 if expected_count <= 0 else covered_count / expected_count

    group_targets = {'factual': 1, 'evidentiary': 0, 'anchor': 0}
    if weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
        group_targets['evidentiary'] = 1
    if weak_complaint_types.intersection({'housing_discrimination', 'hacc_research_engine'}):
        group_targets['factual'] = 2
        group_targets['anchor'] = 1
    if (
        should_frontload_anchor_adverse_action
        or should_frontload_anchor_appeal_rights
        or should_frontload_anchor_grievance_hearing
    ):
        group_targets['anchor'] = max(group_targets['anchor'], 2)
    group_covered_counts = {
        group: len(grouped_covered.get(group, []))
        for group in ('factual', 'evidentiary', 'anchor')
    }
    group_target_met = {
        group: group_covered_counts.get(group, 0) >= group_targets.get(group, 0)
        for group in group_targets
    }

    expected_weight = 0.0
    covered_weight = 0.0
    for objective in expected_objectives:
        weight = cls._intake_objective_weight(objective, optimizer_context)
        expected_weight += weight
        if coverage_counts.get(objective, 0) > 0:
            covered_weight += weight

    forced_uncovered = [
        objective for objective in sorted(forced_objectives)
        if coverage_counts.get(objective, 0) <= 0
    ]
    priority_uncovered: List[str] = []
    if should_frontload_anchor_appeal_rights and coverage_counts.get('anchor_appeal_rights', 0) <= 0:
        priority_uncovered.append('anchor_appeal_rights')
    if should_frontload_anchor_grievance_hearing and coverage_counts.get('anchor_grievance_hearing', 0) <= 0:
        priority_uncovered.append('anchor_grievance_hearing')
    if should_frontload_anchor_adverse_action and coverage_counts.get('anchor_adverse_action', 0) <= 0:
        priority_uncovered.append('anchor_adverse_action')
    if should_frontload_anchor_selection and coverage_counts.get('anchor_selection_criteria', 0) <= 0:
        priority_uncovered.append('anchor_selection_criteria')
    if should_frontload_hearing_request_timing and coverage_counts.get('hearing_request_timing', 0) <= 0:
        priority_uncovered.append('hearing_request_timing')
    if should_frontload_staff_names_titles and coverage_counts.get('staff_names_titles', 0) <= 0:
        priority_uncovered.append('staff_names_titles')
    if should_frontload_causation_sequence and coverage_counts.get('causation_sequence', 0) <= 0:
        priority_uncovered.append('causation_sequence')
    priority_uncovered_evidence_anchors = {
        objective: cls._strongest_evidence_anchor_for_objective(objective, weak_evidence_modalities)
        for objective in priority_uncovered
    }
    recovery_actions: List[str] = []
    if stability_recovery_mode:
        recovery_actions = [
            "Prioritize stable session flow by preserving mediator-generated intake ordering.",
            "Inject only missing intake objectives with a small synthetic-question budget.",
            "Defer aggressive actor-critic ranking adjustments until intake signals recover above baseline.",
        ]

    weighted_coverage = 0.0 if expected_weight <= 0.0 else covered_weight / expected_weight
    exit_ready = (
        (not forced_uncovered)
        and (not priority_uncovered)
        and all(group_target_met.values())
        and (weighted_coverage >= 0.72 or stability_recovery_mode)
    )

    return {
        "expected_objectives": expected_objectives,
        "covered_objectives": covered_objectives,
        "uncovered_objectives": uncovered_objectives,
        "objective_question_counts": coverage_counts,
        "grouped_expected_objectives": grouped_expected,
        "grouped_covered_objectives": grouped_covered,
        "grouped_uncovered_objectives": grouped_uncovered,
        "group_coverage_rates": group_coverage_rates,
        "group_target_minimums": group_targets,
        "group_covered_counts": group_covered_counts,
        "group_target_met": group_target_met,
        "forced_objectives": sorted(forced_objectives),
        "forced_uncovered_objectives": forced_uncovered,
        "priority_uncovered_objectives": priority_uncovered,
        "priority_uncovered_evidence_anchors": priority_uncovered_evidence_anchors,
        "anchor_first_objective_ordering": [
            objective
            for objective in expected_objectives
            if objective in {'anchor_grievance_hearing', 'anchor_selection_criteria', 'intake_follow_up'}
        ],
        "weighted_coverage_score": weighted_coverage,
        "weighted_expected_total": expected_weight,
        "weighted_covered_total": covered_weight,
        "intake_exit_ready": exit_ready,
        "stability_recovery_mode": stability_recovery_mode,
        "stability_recovery_actions": recovery_actions,
        "actor_critic_focus": {
            "weak_complaint_types": sorted(set(optimizer_context.get('weak_complaint_types') or set())),
            "weak_evidence_modalities": sorted(set(optimizer_context.get('weak_evidence_modalities') or set())),
            "question_quality_signal": optimizer_context.get('question_quality'),
            "empathy_signal": optimizer_context.get('empathy'),
            "efficiency_signal": optimizer_context.get('efficiency'),
        },
    }


def _select_next_question(
    self,
    questions: List[Any],
    asked_question_counts: Dict[str, int] | None = None,
    asked_intent_counts: Dict[str, int] | None = None,
    need_timeline: bool = False,
    need_harm_remedy: bool = False,
    need_actor_decisionmaker: bool = False,
    need_causation: bool = False,
    need_documentary_evidence: bool = False,
    need_witness: bool = False,
    need_exact_dates: bool = False,
    need_staff_names_titles: bool = False,
    need_hearing_request_timing: bool = False,
    need_response_dates: bool = False,
    need_causation_sequence: bool = False,
    last_question_key: str | None = None,
    last_question_intent_key: str | None = None,
    recent_intent_keys: Set[str] | None = None,
    missing_anchor_sections: Set[str] | None = None,
) -> Any:
    if not questions:
        return None

    asked_question_counts = dict(asked_question_counts or {})
    asked_intent_counts = dict(asked_intent_counts or {})
    recent_intent_keys = set(recent_intent_keys or set())
    missing_anchor_sections = set(missing_anchor_sections or set())

    seen_question_keys = [k for k, count in asked_question_counts.items() if count > 0]
    candidate_keys_in_turn: Set[str] = set()
    novel_similarity_threshold = 0.7
    rephrase_similarity_threshold = 0.65
    candidates = []
    for q in questions:
        text = self._extract_question_text(q)
        key = self._question_dedupe_key(text)
        if not key or key in candidate_keys_in_turn:
            # Skip empty and duplicate prompts emitted in the same mediator step.
            continue
        candidate_keys_in_turn.add(key)
        intent_key = self._question_intent_key(text, q)
        asked_count = asked_question_counts.get(key, 0)
        intent_count = asked_intent_counts.get(intent_key, 0)
        similarity_to_seen = 0.0
        if seen_question_keys:
            similarity_to_seen = max(
                self._question_similarity(text, seen_key)
                for seen_key in seen_question_keys
            )
        candidates.append((
            q,
            text,
            key,
            intent_key,
            asked_count,
            intent_count,
            similarity_to_seen,
        ))

    if not candidates:
        return None

    non_redundant_candidates = [
        c for c in candidates
        if not self._is_redundant_candidate(
            key=c[2],
            intent_key=c[3],
            asked_count=c[4],
            intent_count=c[5],
            similarity_to_seen=c[6],
            last_question_key=last_question_key,
            last_question_intent_key=last_question_intent_key,
            recent_intent_keys=recent_intent_keys,
        )
    ]
    for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
        if (
            self._is_contradiction_resolution_question(q)
            and asked_count == 0
            and intent_count == 0
            and similarity_to_seen < novel_similarity_threshold
        ):
            return q
    if need_timeline:
        has_timeline_candidate = any(
            self._is_timeline_question(c[0]) for c in non_redundant_candidates
        )
        if not has_timeline_candidate:
            return None

    if need_documentary_evidence:
        has_document_candidate = any(
            self._is_documentary_evidence_question(c[0]) for c in non_redundant_candidates
        )
        if not has_document_candidate:
            return None
    need_adverse_action_details = need_actor_decisionmaker
    # Prefer filling high-value information gaps before exploring lower-value variants.
    high_quality_candidates = [
        c
        for c in non_redundant_candidates
        if (
            self._question_quality_score(c[0], c[1]) >= 0.5
            or self._question_specificity_score(c[1]) >= 0.45
            or self._normalized_actor_critic_score(c[0]) >= 0.5
            or self._extract_selector_score(c[0]) > 0.0
        )
    ]
    if high_quality_candidates:
        non_redundant_candidates = high_quality_candidates
    non_redundant_candidates.sort(
        key=lambda c: (
            self._coverage_gap_rank(
                c[0],
                need_timeline=need_timeline,
                need_harm_remedy=need_harm_remedy,
                need_actor_decisionmaker=need_actor_decisionmaker,
                need_adverse_action_details=need_adverse_action_details,
                need_causation=need_causation,
                need_documentary_evidence=need_documentary_evidence,
                need_witness=need_witness,
                need_exact_dates=need_exact_dates,
                need_staff_names_titles=need_staff_names_titles,
                need_hearing_request_timing=need_hearing_request_timing,
                need_response_dates=need_response_dates,
                need_causation_sequence=need_causation_sequence,
                missing_anchor_sections=missing_anchor_sections,
            ),
            self._phase_focus_rank_for_candidate(c[0]),
            -self._extract_blocker_closure_match_count(c[0]),
            -self._question_quality_score(c[0], c[1]),
            -self._normalized_actor_critic_score(c[0]),
            -self._extract_selector_score(c[0]),
            -self._extract_actor_critic_score(c[0]),
            c[5],
            c[4],
            c[6],
        )
    )
    if need_exact_dates:
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_exact_dates_question(q)
            ):
                return q
    if need_staff_names_titles:
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_staff_names_titles_question(q)
            ):
                return q
    if need_hearing_request_timing:
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_hearing_request_timing_question(q)
            ):
                return q
    if need_response_dates:
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_response_dates_question(q)
            ):
                return q
    if need_adverse_action_details:
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_adverse_action_detail_question(q)
            ):
                return q
    if need_causation_sequence:
        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_causation_sequence_question(q)
            ):
                return q

    if need_harm_remedy:
        for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_harm_or_remedy_question(q)
            ):
                return q

    if need_timeline:
        for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_timeline_question(q)
            ):
                return q

    if need_actor_decisionmaker:
        for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_actor_or_decisionmaker_question(q)
            ):
                return q

    if need_causation:
        for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_protected_activity_causation_question(q)
            ):
                return q

    if need_documentary_evidence:
        for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_documentary_evidence_question(q)
            ):
                return q

    if need_witness:
        for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
                and self._is_witness_question(q)
            ):
                return q

    for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
        if (
            asked_count == 0
            and intent_count == 0
            and similarity_to_seen < novel_similarity_threshold
        ):
            return q

    # Fall back to any unseen question if all options are close in wording.
    for q, _, _, _, asked_count, intent_count, _ in non_redundant_candidates:
        if asked_count == 0 and intent_count == 0:
            return q

    if need_timeline or need_harm_remedy:
        for q, text, key, _, asked_count, _, _ in candidates:
            if asked_count > 0 or key == last_question_key:
                continue
            if need_timeline and self._is_timeline_question(q):
                return q
            if need_harm_remedy and self._is_harm_or_remedy_question(q):
                return q

    # As a last resort, allow one rephrase on a covered intent only if we still
    # need timeline or harm/remedy coverage and the wording is meaningfully different.
    for q, text, key, _, asked_count, intent_count, similarity_to_seen in candidates:
        if (
            asked_count == 0
            and intent_count == 1
            and key != last_question_key
            and similarity_to_seen < rephrase_similarity_threshold
            and (
                (need_timeline and self._is_timeline_question(q))
                or (need_harm_remedy and self._is_harm_or_remedy_question(q))
            )
        ):
            return q

    return None
