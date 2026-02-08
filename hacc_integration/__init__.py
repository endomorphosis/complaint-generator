"""
HACC Integration Module (DEPRECATED)

⚠️ DEPRECATED: This module is deprecated and maintained only for backward compatibility.
Please use 'complaint_analysis' module instead, which provides the same functionality
with an extensible architecture supporting multiple complaint types.

Migration guide:
    Old: from hacc_integration import ComplaintLegalPatternExtractor
    New: from complaint_analysis import LegalPatternExtractor
    
    Old: from hacc_integration import ComplaintRiskScorer
    New: from complaint_analysis import ComplaintRiskScorer
    
See complaint_analysis module documentation for more details.

This module extracts and adapts the legal domain knowledge from the HACC repository
for use with ipfs_datasets_py infrastructure. It provides:

1. Legal term patterns for complaint-relevant legal text extraction
2. Complaint-specific keyword taxonomies
3. Risk scoring algorithms for complaints
4. Report generation templates
"""

import warnings

# Issue deprecation warning when module is imported
warnings.warn(
    "The 'hacc_integration' module is deprecated. "
    "Please use 'complaint_analysis' module instead. "
    "See complaint_analysis/README.md for migration guide.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from complaint_analysis for backward compatibility
from complaint_analysis import (
    LegalPatternExtractor as ComplaintLegalPatternExtractor,
    COMPLAINT_LEGAL_TERMS,
    COMPLAINT_KEYWORDS,
    EVIDENCE_KEYWORDS,
    LEGAL_AUTHORITY_KEYWORDS,
    APPLICABILITY_KEYWORDS,
    ComplaintRiskScorer,
    HybridDocumentIndexer
)

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

__version__ = '1.0.0 (deprecated - use complaint_analysis v2.0.0+)'
