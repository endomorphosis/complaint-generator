"""
Complaint Phases Module

This module implements a three-phase complaint processing system:
1. Initial Intake & Denoising - Generate knowledge/dependency graphs, ask questions
2. Evidence Gathering - Enhance graphs with evidence, fill gaps
3. Neurosymbolic Representation - Match against law graphs, generate formal complaint
"""

from .knowledge_graph import (
    KnowledgeGraphBuilder, 
    KnowledgeGraph, 
    Entity, 
    Relationship
)
from .dependency_graph import (
    DependencyGraphBuilder, 
    DependencyGraph,
    DependencyNode,
    Dependency,
    NodeType,
    DependencyType
)
from .denoiser import ComplaintDenoiser
from .intake_case_file import (
    build_intake_case_file,
    confirm_intake_summary,
    refresh_intake_case_file,
    refresh_intake_sections,
)
from .intake_claim_registry import (
    CLAIM_INTAKE_REQUIREMENTS,
    build_claim_element_question_intent,
    build_claim_element_question_text,
    build_proof_lead_question_intent,
    build_proof_lead_question_text,
    match_required_element_id,
    normalize_claim_type,
    render_question_text_from_intent,
)
from .phase_manager import PhaseManager, ComplaintPhase
from .legal_graph import (
    LegalGraphBuilder, 
    LegalGraph,
    LegalElement,
    LegalRelation
)
from .deontic_logic import (
    DeonticGraphBuilder,
    DeonticGraph,
    DeonticNode,
    DeonticRule,
    DeonticNodeType,
    DeonticModality,
)
from .legal_document import (
    PleadingHeader,
    PleadingCaption,
    DocumentSection,
    ParsedLegalDocument,
    build_pleading_caption,
    extract_pleading_header,
    paginate_pleading_lines,
    parse_legal_document,
    render_pleading_caption_block,
)
from .support_map import (
    FilingSupportReference,
    MotionSupportMap,
    SupportFact,
    SupportMapBuilder,
    SupportMapEntry,
)
from .neurosymbolic_matcher import NeurosymbolicMatcher

__all__ = [
    'KnowledgeGraphBuilder',
    'KnowledgeGraph',
    'Entity',
    'Relationship',
    'DependencyGraphBuilder',
    'DependencyGraph',
    'DependencyNode',
    'Dependency',
    'NodeType',
    'DependencyType',
    'ComplaintDenoiser',
    'build_intake_case_file',
    'confirm_intake_summary',
    'refresh_intake_case_file',
    'refresh_intake_sections',
    'CLAIM_INTAKE_REQUIREMENTS',
    'build_claim_element_question_intent',
    'build_claim_element_question_text',
    'build_proof_lead_question_intent',
    'build_proof_lead_question_text',
    'match_required_element_id',
    'normalize_claim_type',
    'render_question_text_from_intent',
    'PhaseManager',
    'ComplaintPhase',
    'LegalGraphBuilder',
    'LegalGraph',
    'LegalElement',
    'LegalRelation',
    'DeonticGraphBuilder',
    'DeonticGraph',
    'DeonticNode',
    'DeonticRule',
    'DeonticNodeType',
    'DeonticModality',
    'PleadingHeader',
    'PleadingCaption',
    'DocumentSection',
    'ParsedLegalDocument',
    'build_pleading_caption',
    'extract_pleading_header',
    'paginate_pleading_lines',
    'parse_legal_document',
    'render_pleading_caption_block',
    'FilingSupportReference',
    'MotionSupportMap',
    'SupportFact',
    'SupportMapBuilder',
    'SupportMapEntry',
    'NeurosymbolicMatcher',
]
