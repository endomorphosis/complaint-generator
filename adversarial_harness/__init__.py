"""
Adversarial Test Harness and Optimizer

This module implements an adversarial system using LLM inference to optimize
the mediator's ability to generate good questions from complainants.

Components:
- Complainant: LLM-based complaint generator and responder
- Mediator: System under test (uses existing mediator)
- Critic: LLM-based evaluator that ranks interaction quality
- AdversarialSession: Single rollout/episode
- AdversarialHarness: Orchestrator for multiple sessions
- Optimizer: Analyzes critic feedback to improve mediator
- Search Hooks: Integration with Brave search and legal corpus RAG
"""

from importlib import import_module

_LAZY_EXPORTS = {
    'Complainant': ('.complainant', 'Complainant'),
    'ComplaintGenerator': ('.complainant', 'ComplaintGenerator'),
    'ComplaintContext': ('.complainant', 'ComplaintContext'),
    'Critic': ('.critic', 'Critic'),
    'CriticScore': ('.critic', 'CriticScore'),
    'AdversarialSession': ('.session', 'AdversarialSession'),
    'SessionResult': ('.session', 'SessionResult'),
    'AdversarialHarness': ('.harness', 'AdversarialHarness'),
    'Optimizer': ('.optimizer', 'Optimizer'),
    'OptimizationReport': ('.optimizer', 'OptimizationReport'),
    'WorkflowOptimizationBundle': ('.optimizer', 'WorkflowOptimizationBundle'),
    'UIOptimizationBundle': ('.optimizer', 'UIOptimizationBundle'),
    'UIUXOptimizationBundle': ('.optimizer', 'UIUXOptimizationBundle'),
    'SeedComplaintLibrary': ('.seed_complaints', 'SeedComplaintLibrary'),
    'ComplaintTemplate': ('.seed_complaints', 'ComplaintTemplate'),
    'build_hacc_evidence_seeds': ('.hacc_evidence', 'build_hacc_evidence_seeds'),
    'DEFAULT_HACC_QUERY_SPECS': ('.hacc_evidence', 'DEFAULT_HACC_QUERY_SPECS'),
    'HACC_QUERY_PRESETS': ('.hacc_evidence', 'HACC_QUERY_PRESETS'),
    'get_hacc_query_specs': ('.hacc_evidence', 'get_hacc_query_specs'),
    'SearchEnrichedSeedGenerator': ('.search_hooks', 'SearchEnrichedSeedGenerator'),
    'DecisionTreeEnhancer': ('.search_hooks', 'DecisionTreeEnhancer'),
    'MediatorSearchIntegration': ('.search_hooks', 'MediatorSearchIntegration'),
}

__all__ = [
    'Complainant',
    'ComplaintGenerator',
    'ComplaintContext',
    'Critic',
    'CriticScore',
    'AdversarialSession',
    'SessionResult',
    'AdversarialHarness',
    'Optimizer',
    'OptimizationReport',
    'WorkflowOptimizationBundle',
    'UIOptimizationBundle',
    'UIUXOptimizationBundle',
    'SeedComplaintLibrary',
    'ComplaintTemplate',
    'build_hacc_evidence_seeds',
    'DEFAULT_HACC_QUERY_SPECS',
    'HACC_QUERY_PRESETS',
    'get_hacc_query_specs',
    'SearchEnrichedSeedGenerator',
    'DecisionTreeEnhancer',
    'MediatorSearchIntegration',
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = module if attribute_name is None else getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
