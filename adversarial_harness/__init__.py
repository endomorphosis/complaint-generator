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
"""

from .complainant import Complainant, ComplaintGenerator, ComplaintContext
from .critic import Critic, CriticScore
from .session import AdversarialSession, SessionResult
from .harness import AdversarialHarness
from .optimizer import Optimizer, OptimizationReport
from .seed_complaints import SeedComplaintLibrary, ComplaintTemplate

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
    'SeedComplaintLibrary',
    'ComplaintTemplate',
]
