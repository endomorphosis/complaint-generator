from __future__ import annotations

from datetime import datetime

from lib.formal_logic import (
    Action,
    Conjunction,
    DeonticKnowledgeBase,
    DeonticModality,
    DeonticStatement,
    Party,
    Predicate,
    TimeInterval,
)


def test_time_interval_resolves_end_and_contains_dates() -> None:
    interval = TimeInterval(start=datetime(2026, 4, 1), duration_days=5)

    assert interval.resolved_end() == datetime(2026, 4, 6)
    assert interval.contains(datetime(2026, 4, 1)) is True
    assert interval.contains(datetime(2026, 4, 4)) is True
    assert interval.contains(datetime(2026, 4, 7)) is False


def test_predicates_and_implication_style_conditions_evaluate_against_model() -> None:
    condition = Conjunction(
        Predicate("has_notice", ("tenant_1",)),
        Predicate("needs_accommodation", ("tenant_1",)),
    )
    model = {
        "has_notice(tenant_1)": True,
        "needs_accommodation(tenant_1)": True,
    }

    assert condition.evaluate(model) is True


def test_deontic_knowledge_base_infers_rule_bound_statement_and_checks_compliance() -> None:
    kb = DeonticKnowledgeBase()
    authority = Party(name="Housing Authority", role="agency", entity_id="agency:hacc")
    tenant = Party(name="Tenant", role="resident", entity_id="resident:1")
    action = Action(verb="provide", object_noun="accessible hearing", action_id="action:hearing")
    statement = DeonticStatement(
        modality=DeonticModality.OBLIGATORY,
        actor=authority,
        action=action,
        recipient=tenant,
        time_interval=TimeInterval(start=datetime(2026, 2, 13), duration_days=30),
    )
    kb.add_rule(Predicate("termination_notice_served", (authority, tenant)), statement)
    kb.add_fact(f"termination_notice_served({authority}, {tenant})")

    inferred = kb.infer_statements()

    assert statement in inferred
    assert kb.get_statements(modality=DeonticModality.OBLIGATORY, actor=authority) == {statement}
    compliant, reason = kb.check_compliance(authority, action, datetime(2026, 2, 20))
    assert compliant is True
    assert "complies with obligation" in reason