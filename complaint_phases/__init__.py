"""
Complaint Phases Module

This module implements a three-phase complaint processing system:
1. Initial Intake & Denoising - Generate knowledge/dependency graphs, ask questions
2. Evidence Gathering - Enhance graphs with evidence, fill gaps
3. Neurosymbolic Representation - Match against law graphs, generate formal complaint
"""

from importlib import import_module

_LAZY_EXPORTS = {
    'KnowledgeGraphBuilder': ('.knowledge_graph', 'KnowledgeGraphBuilder'),
    'KnowledgeGraph': ('.knowledge_graph', 'KnowledgeGraph'),
    'Entity': ('.knowledge_graph', 'Entity'),
    'Relationship': ('.knowledge_graph', 'Relationship'),
    'DependencyGraphBuilder': ('.dependency_graph', 'DependencyGraphBuilder'),
    'DependencyGraph': ('.dependency_graph', 'DependencyGraph'),
    'DependencyNode': ('.dependency_graph', 'DependencyNode'),
    'Dependency': ('.dependency_graph', 'Dependency'),
    'NodeType': ('.dependency_graph', 'NodeType'),
    'DependencyType': ('.dependency_graph', 'DependencyType'),
    'ComplaintDenoiser': ('.denoiser', 'ComplaintDenoiser'),
    'build_intake_case_file': ('.intake_case_file', 'build_intake_case_file'),
    'confirm_intake_summary': ('.intake_case_file', 'confirm_intake_summary'),
    'refresh_intake_case_file': ('.intake_case_file', 'refresh_intake_case_file'),
    'refresh_intake_sections': ('.intake_case_file', 'refresh_intake_sections'),
    'CLAIM_INTAKE_REQUIREMENTS': ('.intake_claim_registry', 'CLAIM_INTAKE_REQUIREMENTS'),
    'build_claim_element_question_intent': ('.intake_claim_registry', 'build_claim_element_question_intent'),
    'build_claim_element_question_text': ('.intake_claim_registry', 'build_claim_element_question_text'),
    'build_proof_lead_question_intent': ('.intake_claim_registry', 'build_proof_lead_question_intent'),
    'build_proof_lead_question_text': ('.intake_claim_registry', 'build_proof_lead_question_text'),
    'match_required_element_id': ('.intake_claim_registry', 'match_required_element_id'),
    'normalize_claim_type': ('.intake_claim_registry', 'normalize_claim_type'),
    'render_question_text_from_intent': ('.intake_claim_registry', 'render_question_text_from_intent'),
    'PhaseManager': ('.phase_manager', 'PhaseManager'),
    'ComplaintPhase': ('.phase_manager', 'ComplaintPhase'),
    'LegalGraphBuilder': ('.legal_graph', 'LegalGraphBuilder'),
    'LegalGraph': ('.legal_graph', 'LegalGraph'),
    'LegalElement': ('.legal_graph', 'LegalElement'),
    'LegalRelation': ('.legal_graph', 'LegalRelation'),
    'DeonticGraphBuilder': ('.deontic_logic', 'DeonticGraphBuilder'),
    'DeonticGraph': ('.deontic_logic', 'DeonticGraph'),
    'DeonticNode': ('.deontic_logic', 'DeonticNode'),
    'DeonticRule': ('.deontic_logic', 'DeonticRule'),
    'DeonticNodeType': ('.deontic_logic', 'DeonticNodeType'),
    'DeonticModality': ('.deontic_logic', 'DeonticModality'),
    'PleadingHeader': ('.legal_document', 'PleadingHeader'),
    'PleadingCaption': ('.legal_document', 'PleadingCaption'),
    'DocumentSection': ('.legal_document', 'DocumentSection'),
    'ParsedLegalDocument': ('.legal_document', 'ParsedLegalDocument'),
    'build_pleading_caption': ('.legal_document', 'build_pleading_caption'),
    'extract_pleading_header': ('.legal_document', 'extract_pleading_header'),
    'paginate_pleading_lines': ('.legal_document', 'paginate_pleading_lines'),
    'parse_legal_document': ('.legal_document', 'parse_legal_document'),
    'render_pleading_caption_block': ('.legal_document', 'render_pleading_caption_block'),
    'FilingSupportReference': ('.support_map', 'FilingSupportReference'),
    'MotionSupportMap': ('.support_map', 'MotionSupportMap'),
    'SupportFact': ('.support_map', 'SupportFact'),
    'SupportMapBuilder': ('.support_map', 'SupportMapBuilder'),
    'SupportMapEntry': ('.support_map', 'SupportMapEntry'),
    'NeurosymbolicMatcher': ('.neurosymbolic_matcher', 'NeurosymbolicMatcher'),
}

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
