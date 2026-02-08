"""
Complaint Type Registration

Provides convenience functions for registering different complaint types
with their specific keywords, patterns, and scoring models.
"""

from typing import Dict, List
from .keywords import register_keywords
from .legal_patterns import register_legal_terms


def register_housing_complaint():
    """Register keywords and patterns for housing complaints."""
    # Already registered in keywords.py, but this allows for programmatic registration
    pass


def register_employment_complaint():
    """Register keywords and patterns for employment complaints."""
    # Already registered in keywords.py
    pass


def register_civil_rights_complaint():
    """Register keywords and patterns for civil rights complaints."""
    # Additional civil rights specific keywords
    register_keywords('complaint', [
        'police brutality', 'excessive force',
        'unlawful search', 'unlawful seizure',
        'first amendment', 'freedom of speech',
        'freedom of assembly', 'voting rights',
    ], complaint_type='civil_rights')


def register_consumer_complaint():
    """Register keywords and patterns for consumer protection complaints."""
    register_keywords('complaint', [
        'fraud', 'deception', 'misrepresentation',
        'unfair practice', 'deceptive practice',
        'false advertising', 'bait and switch',
        'warranty breach', 'consumer protection',
        'ftc', 'federal trade commission',
    ], complaint_type='consumer')
    
    register_legal_terms('consumer', [
        r'\b(fraud|fraudulent)\b',
        r'\b(deceptive (practice|trade))\b',
        r'\b(false advertising)\b',
        r'\b(consumer protection)\b',
        r'\b(ftc|federal trade commission)\b',
    ])


def register_healthcare_complaint():
    """Register keywords and patterns for healthcare complaints."""
    register_keywords('complaint', [
        'medical malpractice', 'negligence',
        'hipaa', 'medical privacy',
        'patient rights', 'informed consent',
        'emergency medical', 'emtala',
    ], complaint_type='healthcare')


def get_registered_types() -> List[str]:
    """
    Get all registered complaint types.
    
    Returns:
        List of complaint type names
    """
    from .keywords import _global_registry
    return _global_registry.get_complaint_types()


# Register default types on module import
register_housing_complaint()
register_employment_complaint()
register_civil_rights_complaint()
