"""Reusable formal-logic primitives for complaint-generator."""

from importlib import import_module

_LAZY_EXPORTS = {
    "Action": (".core", "Action"),
    "Conjunction": (".core", "Conjunction"),
    "DeonticKnowledgeBase": (".core", "DeonticKnowledgeBase"),
    "DeonticModality": (".core", "DeonticModality"),
    "DeonticStatement": (".core", "DeonticStatement"),
    "Disjunction": (".core", "Disjunction"),
    "Frame": (".frames", "Frame"),
    "FrameKnowledgeBase": (".frames", "FrameKnowledgeBase"),
    "FrameSlotEvidence": (".frames", "FrameSlotEvidence"),
    "CANONICAL_COMPILER_CAPABILITY_SCHEMA": (".capabilities", "CANONICAL_COMPILER_CAPABILITY_SCHEMA"),
    "CanonicalCompilerCapability": (".capabilities", "CanonicalCompilerCapability"),
    "CanonicalCompilerSupport": (".capabilities", "CanonicalCompilerSupport"),
    "FormalLogicCapability": (".capabilities", "FormalLogicCapability"),
    "FormalLogicCapabilityError": (".capabilities", "FormalLogicCapabilityError"),
    "FormalLogicDegradedError": (".capabilities", "FormalLogicDegradedError"),
    "FormalLogicOperation": (".capabilities", "FormalLogicOperation"),
    "FormalLogicUnavailableError": (".capabilities", "FormalLogicUnavailableError"),
    "Implication": (".core", "Implication"),
    "LogicalOperator": (".core", "LogicalOperator"),
    "LogicCapabilityState": (".capabilities", "LogicCapabilityState"),
    "LogicCapabilityStatus": (".capabilities", "LogicCapabilityStatus"),
    "capability_state_from_payload": (".capabilities", "capability_state_from_payload"),
    "classify_canonical_compiler_capability": (".capabilities", "classify_canonical_compiler_capability"),
    "Negation": (".core", "Negation"),
    "Party": (".core", "Party"),
    "Predicate": (".core", "Predicate"),
    "Proposition": (".core", "Proposition"),
    "TemporalOperator": (".core", "TemporalOperator"),
    "TimeInterval": (".core", "TimeInterval"),
}

__all__ = [
    "Action",
    "Conjunction",
    "DeonticKnowledgeBase",
    "DeonticModality",
    "DeonticStatement",
    "Disjunction",
    "Frame",
    "FrameKnowledgeBase",
    "FrameSlotEvidence",
    "CANONICAL_COMPILER_CAPABILITY_SCHEMA",
    "CanonicalCompilerCapability",
    "CanonicalCompilerSupport",
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "Implication",
    "LogicalOperator",
    "LogicCapabilityState",
    "LogicCapabilityStatus",
    "capability_state_from_payload",
    "classify_canonical_compiler_capability",
    "Negation",
    "Party",
    "Predicate",
    "Proposition",
    "TemporalOperator",
    "TimeInterval",
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
