"""
Complaint Analysis Module

A flexible, extensible framework for analyzing legal complaints across different
domains (housing, employment, civil rights, consumer protection, etc.).

This module provides:
1. Extensible legal term pattern extraction
2. Configurable keyword taxonomies for different complaint types
3. Pluggable risk scoring algorithms
4. Hybrid document indexing (vector + keyword)

The framework is designed to be extended with new complaint types by:
- Registering new keyword sets
- Adding new legal pattern categories
- Implementing custom risk scorers

Example:
    >>> from complaint_analysis import ComplaintAnalyzer
    >>> analyzer = ComplaintAnalyzer(complaint_type='housing')
    >>> result = analyzer.analyze(document_text)
    >>> print(f"Risk: {result['risk_level']}, Categories: {result['categories']}")
"""

from importlib import import_module

_LAZY_EXPORTS = {
    'BaseLegalPatternExtractor': ('.base', 'BaseLegalPatternExtractor'),
    'BaseKeywordRegistry': ('.base', 'BaseKeywordRegistry'),
    'BaseRiskScorer': ('.base', 'BaseRiskScorer'),
    'LegalPatternExtractor': ('.legal_patterns', 'LegalPatternExtractor'),
    'ComplaintLegalPatternExtractor': ('.legal_patterns', 'LegalPatternExtractor'),
    'KeywordRegistry': ('.keywords', 'KeywordRegistry'),
    'ComplaintRiskScorer': ('.risk_scoring', 'ComplaintRiskScorer'),
    'DEIRiskScorer': ('.dei_risk_scoring', 'DEIRiskScorer'),
    'DEIProvisionExtractor': ('.dei_provision_extractor', 'DEIProvisionExtractor'),
    'DEIReportGenerator': ('.dei_report_generator', 'DEIReportGenerator'),
    'RiskScorer': ('.risk_scoring', 'ComplaintRiskScorer'),
    'HybridDocumentIndexer': ('.indexer', 'HybridDocumentIndexer'),
    'ComplaintAnalyzer': ('.analyzer', 'ComplaintAnalyzer'),
    'SeedGenerator': ('.seed_generator', 'SeedGenerator'),
    'SeedComplaintTemplate': ('.seed_generator', 'SeedComplaintTemplate'),
    'DecisionTreeGenerator': ('.decision_trees', 'DecisionTreeGenerator'),
    'DecisionTree': ('.decision_trees', 'DecisionTree'),
    'QuestionNode': ('.decision_trees', 'QuestionNode'),
    'PromptTemplate': ('.prompt_templates', 'PromptTemplate'),
    'PromptLibrary': ('.prompt_templates', 'PromptLibrary'),
    'ReturnFormat': ('.prompt_templates', 'ReturnFormat'),
    'BaseResponseParser': ('.response_parsers', 'BaseResponseParser'),
    'JSONResponseParser': ('.response_parsers', 'JSONResponseParser'),
    'StructuredTextParser': ('.response_parsers', 'StructuredTextParser'),
    'EntityParser': ('.response_parsers', 'EntityParser'),
    'RelationshipParser': ('.response_parsers', 'RelationshipParser'),
    'QuestionParser': ('.response_parsers', 'QuestionParser'),
    'ClaimParser': ('.response_parsers', 'ClaimParser'),
    'StateFileIngester': ('.response_parsers', 'StateFileIngester'),
    'ResponseParserFactory': ('.response_parsers', 'ResponseParserFactory'),
    'ParsedResponse': ('.response_parsers', 'ParsedResponse'),
    'build_download_queue': ('.research_queue_workflow', 'build_download_queue'),
    'download_queue': ('.research_queue_workflow', 'download_queue'),
    'filter_download_queue': ('.research_queue_workflow', 'filter_download_queue'),
    'extract_external_document_queue': ('.research_bootstrap_workflow', 'extract_external_document_queue'),
    'extract_third_party_candidates_from_corpus': ('.research_bootstrap_workflow', 'extract_third_party_candidates_from_corpus'),
    'load_manifest_rows': ('.research_bootstrap_workflow', 'load_manifest_rows'),
    'write_candidates_csv': ('.research_bootstrap_workflow', 'write_candidates_csv'),
    'get_keywords': ('.keywords', 'get_keywords'),
    'get_type_specific_keywords': ('.keywords', 'get_type_specific_keywords'),
    'register_keywords': ('.keywords', 'register_keywords'),
    'register_legal_terms': ('.legal_patterns', 'register_legal_terms'),
    'get_legal_terms': ('.legal_patterns', 'get_legal_terms'),
    'COMPLAINT_KEYWORDS': ('.keywords', 'COMPLAINT_KEYWORDS'),
    'EVIDENCE_KEYWORDS': ('.keywords', 'EVIDENCE_KEYWORDS'),
    'LEGAL_AUTHORITY_KEYWORDS': ('.keywords', 'LEGAL_AUTHORITY_KEYWORDS'),
    'APPLICABILITY_KEYWORDS': ('.keywords', 'APPLICABILITY_KEYWORDS'),
    'LEGAL_TERMS_REGISTRY': ('.legal_patterns', 'LEGAL_TERMS_REGISTRY'),
    'COMPLAINT_LEGAL_TERMS': ('.legal_patterns', 'COMPLAINT_LEGAL_TERMS'),
    'register_housing_complaint': ('.complaint_types', 'register_housing_complaint'),
    'register_employment_complaint': ('.complaint_types', 'register_employment_complaint'),
    'register_civil_rights_complaint': ('.complaint_types', 'register_civil_rights_complaint'),
    'register_consumer_complaint': ('.complaint_types', 'register_consumer_complaint'),
    'register_healthcare_complaint': ('.complaint_types', 'register_healthcare_complaint'),
    'register_free_speech_complaint': ('.complaint_types', 'register_free_speech_complaint'),
    'register_immigration_complaint': ('.complaint_types', 'register_immigration_complaint'),
    'register_family_law_complaint': ('.complaint_types', 'register_family_law_complaint'),
    'register_criminal_defense_complaint': ('.complaint_types', 'register_criminal_defense_complaint'),
    'register_tax_law_complaint': ('.complaint_types', 'register_tax_law_complaint'),
    'register_intellectual_property_complaint': ('.complaint_types', 'register_intellectual_property_complaint'),
    'register_environmental_law_complaint': ('.complaint_types', 'register_environmental_law_complaint'),
    'register_dei_complaint': ('.complaint_types', 'register_dei_complaint'),
    'get_registered_types': ('.complaint_types', 'get_registered_types'),
}

__all__ = [
    'BaseLegalPatternExtractor',
    'BaseKeywordRegistry',
    'BaseRiskScorer',
    'LegalPatternExtractor',
    'ComplaintLegalPatternExtractor',
    'KeywordRegistry',
    'ComplaintRiskScorer',
    'DEIRiskScorer',
    'DEIProvisionExtractor',
    'DEIReportGenerator',
    'RiskScorer',
    'HybridDocumentIndexer',
    'ComplaintAnalyzer',
    'SeedGenerator',
    'SeedComplaintTemplate',
    'DecisionTreeGenerator',
    'DecisionTree',
    'QuestionNode',
    'PromptTemplate',
    'PromptLibrary',
    'ReturnFormat',
    'BaseResponseParser',
    'JSONResponseParser',
    'StructuredTextParser',
    'EntityParser',
    'RelationshipParser',
    'QuestionParser',
    'ClaimParser',
    'StateFileIngester',
    'ResponseParserFactory',
    'ParsedResponse',
    'build_download_queue',
    'download_queue',
    'filter_download_queue',
    'extract_external_document_queue',
    'extract_third_party_candidates_from_corpus',
    'load_manifest_rows',
    'write_candidates_csv',
    'get_keywords',
    'get_type_specific_keywords',
    'register_keywords',
    'register_legal_terms',
    'get_legal_terms',
    'COMPLAINT_KEYWORDS',
    'EVIDENCE_KEYWORDS',
    'LEGAL_AUTHORITY_KEYWORDS',
    'APPLICABILITY_KEYWORDS',
    'LEGAL_TERMS_REGISTRY',
    'COMPLAINT_LEGAL_TERMS',
    'register_housing_complaint',
    'register_employment_complaint',
    'register_civil_rights_complaint',
    'register_consumer_complaint',
    'register_healthcare_complaint',
    'register_free_speech_complaint',
    'register_immigration_complaint',
    'register_family_law_complaint',
    'register_criminal_defense_complaint',
    'register_tax_law_complaint',
    'register_intellectual_property_complaint',
    'register_environmental_law_complaint',
    'register_dei_complaint',
    'get_registered_types',
]

__version__ = '2.0.0'


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
