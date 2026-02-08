"""
Complaint-Specific Keywords

Adapted from HACC's index_and_tag.py - provides keyword taxonomies for
complaint-related document classification and search.

These keyword sets are used for:
1. Hybrid search (combining with vector embeddings)
2. Document tagging and categorization
3. Relevance scoring
4. Evidence filtering
"""

from typing import List, Dict

# Complaint-related keywords (adapted from HACC's DEI_KEYWORDS)
COMPLAINT_KEYWORDS: List[str] = [
    # Discrimination types
    'discrimination', 'discriminate', 'discriminatory',
    'harassment', 'hostile environment',
    'retaliation', 'retaliate', 'retaliatory',
    
    # Fair housing
    'fair housing', 'housing discrimination',
    'reasonable accommodation', 'reasonable modification',
    'familial status', 'source of income',
    
    # Protected classes
    'protected class', 'protected classes',
    'race', 'racial', 'color',
    'national origin', 'nationality',
    'religion', 'religious',
    'sex', 'gender',
    'disability', 'disabled', 'handicap',
    'age', 'elderly',
    'sexual orientation', 'gender identity',
    
    # Legal impact
    'disparate impact', 'disparate treatment',
    'intentional discrimination', 'unintentional discrimination',
    'adverse impact', 'adverse effect',
    
    # Housing specific
    'section 8', 'housing choice voucher',
    'public housing', 'affordable housing',
    'tenant', 'landlord', 'lease', 'rental',
    'eviction', 'housing authority',
    
    # Employment specific
    'employment discrimination', 'workplace discrimination',
    'equal employment opportunity', 'eeoc',
    'title vii', 'ada', 'adea', 'fmla',
    
    # Civil rights
    'civil rights', 'equal protection', 'due process',
    'constitutional rights', 'constitutional violation',
    
    # Complaint process
    'complainant', 'respondent', 'charging party',
    'aggrieved person', 'complaint', 'charge',
]

# Evidence-related keywords
EVIDENCE_KEYWORDS: List[str] = [
    'evidence', 'proof', 'documentation',
    'witness', 'testimony', 'statement',
    'document', 'record', 'file',
    'exhibit', 'attachment', 'appendix',
    'correspondence', 'email', 'letter',
    'notice', 'communication',
    'photograph', 'image', 'video',
    'recording', 'audio',
    'contract', 'agreement', 'lease',
    'policy', 'procedure', 'manual',
    'complaint form', 'intake form',
    'medical record', 'doctor note',
    'police report', 'incident report',
]

# Legal authority keywords
LEGAL_AUTHORITY_KEYWORDS: List[str] = [
    'statute', 'law', 'code', 'regulation',
    'ordinance', 'rule', 'act',
    'u.s.c.', 'c.f.r.', 'federal register',
    'case law', 'precedent', 'holding',
    'opinion', 'decision', 'ruling',
    'court order', 'judgment', 'decree',
    'constitution', 'constitutional',
    'amendment', 'provision', 'section',
    'subsection', 'clause', 'paragraph',
    'title', 'chapter', 'article',
]

# Applicability keywords (from HACC's APPLICABILITY_KEYWORDS)
APPLICABILITY_KEYWORDS: Dict[str, List[str]] = {
    'housing': [
        'housing', 'lease', 'tenant', 'landlord', 'rental',
        'dwelling', 'residence', 'apartment', 'unit',
        'eviction', 'termination', 'nonrenewal',
        'affordable', 'public housing', 'section 8',
        'housing authority', 'housing choice voucher',
        'reasonable accommodation', 'accessibility',
    ],
    
    'employment': [
        'employment', 'workplace', 'job', 'work',
        'hire', 'hiring', 'recruit', 'recruitment',
        'fire', 'firing', 'terminate', 'termination',
        'promote', 'promotion', 'demote', 'demotion',
        'employee', 'employer', 'supervisor',
        'wages', 'salary', 'compensation', 'benefits',
        'fmla', 'leave', 'accommodation',
    ],
    
    'public_accommodation': [
        'public accommodation', 'place of public accommodation',
        'service', 'facility', 'establishment',
        'access', 'accessibility', 'barrier',
        'restaurant', 'hotel', 'store', 'shop',
        'theater', 'stadium', 'park',
        'transportation', 'bus', 'train',
    ],
    
    'lending': [
        'lending', 'loan', 'mortgage', 'credit',
        'financing', 'financial', 'bank', 'lender',
        'interest rate', 'terms', 'approval',
        'denial', 'redlining', 'appraisal',
    ],
    
    'education': [
        'education', 'school', 'university', 'college',
        'student', 'enrollment', 'admission',
        'classroom', 'teacher', 'faculty',
        'curriculum', 'program', 'degree',
        'disability services', 'accommodations',
    ],
    
    'government_services': [
        'government', 'agency', 'department',
        'public service', 'benefits', 'assistance',
        'program', 'eligibility', 'application',
        'permit', 'license', 'approval',
    ],
}

# Binding/enforceable indicators (from HACC's BINDING_KEYWORDS)
BINDING_KEYWORDS: List[str] = [
    'policy', 'ordinance', 'statewide', 'model policy',
    'contract', 'agreement', 'standard',
    'required', 'must', 'shall', 'mandatory',
    'applicable to', 'applicability', 'enforceable',
    'governing', 'binding', 'regulation', 'rule',
    'directive', 'compliance', 'obligated', 'stipulation',
]

# Severity/risk indicators
SEVERITY_KEYWORDS: Dict[str, List[str]] = {
    'high': [
        'systemic', 'pattern', 'practice',
        'intentional', 'willful', 'deliberate',
        'egregious', 'severe', 'pervasive',
        'ongoing', 'repeated', 'continuous',
        'punitive damages', 'injunctive relief',
    ],
    
    'medium': [
        'violation', 'breach', 'failure',
        'inadequate', 'insufficient',
        'disparate impact', 'adverse effect',
        'compensatory damages',
    ],
    
    'low': [
        'potential', 'possible', 'may',
        'unintentional', 'inadvertent',
        'technical', 'procedural',
        'correctable', 'remediable',
    ],
}


def get_all_keywords() -> List[str]:
    """Get all keywords as a flat list (deduplicated)."""
    all_keywords = set()
    all_keywords.update(COMPLAINT_KEYWORDS)
    all_keywords.update(EVIDENCE_KEYWORDS)
    all_keywords.update(LEGAL_AUTHORITY_KEYWORDS)
    all_keywords.update(BINDING_KEYWORDS)
    
    for keywords in APPLICABILITY_KEYWORDS.values():
        all_keywords.update(keywords)
    
    for keywords in SEVERITY_KEYWORDS.values():
        all_keywords.update(keywords)
    
    return sorted(list(all_keywords))


def get_keywords_by_category(category: str) -> List[str]:
    """
    Get keywords for a specific category.
    
    Args:
        category: Category name (e.g., 'housing', 'employment', 'complaint')
        
    Returns:
        List of keywords for that category
    """
    if category == 'complaint':
        return COMPLAINT_KEYWORDS
    elif category == 'evidence':
        return EVIDENCE_KEYWORDS
    elif category == 'legal':
        return LEGAL_AUTHORITY_KEYWORDS
    elif category == 'binding':
        return BINDING_KEYWORDS
    elif category in APPLICABILITY_KEYWORDS:
        return APPLICABILITY_KEYWORDS[category]
    elif category in SEVERITY_KEYWORDS:
        return SEVERITY_KEYWORDS[category]
    else:
        return []
