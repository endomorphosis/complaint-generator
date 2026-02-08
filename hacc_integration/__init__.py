"""
HACC Integration Module

This module extracts and adapts the legal domain knowledge from the HACC repository
for use with ipfs_datasets_py infrastructure. It provides:

1. Legal term patterns for complaint-relevant legal text extraction
2. Complaint-specific keyword taxonomies
3. Risk scoring algorithms for complaints
4. Report generation templates

This represents the unique value of the HACC repository (legal expertise)
integrated with ipfs_datasets_py's superior infrastructure (search, PDF processing, 
storage, knowledge graphs).
"""

from .legal_patterns import ComplaintLegalPatternExtractor, COMPLAINT_LEGAL_TERMS
from .keywords import (
    COMPLAINT_KEYWORDS,
    EVIDENCE_KEYWORDS,
    LEGAL_AUTHORITY_KEYWORDS,
    APPLICABILITY_KEYWORDS
)
from .risk_scoring import ComplaintRiskScorer
from .indexer import HybridDocumentIndexer

__all__ = [
    'ComplaintLegalPatternExtractor',
    'COMPLAINT_LEGAL_TERMS',
    'COMPLAINT_KEYWORDS',
    'EVIDENCE_KEYWORDS',
    'LEGAL_AUTHORITY_KEYWORDS',
    'APPLICABILITY_KEYWORDS',
    'ComplaintRiskScorer',
    'HybridDocumentIndexer',
]

__version__ = '1.0.0'
