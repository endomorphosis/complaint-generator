"""
Extensible Keyword Management for Complaint Analysis

Provides a registry-based system for managing keywords across different
complaint types and categories. Keywords can be registered dynamically for
new complaint types.
"""

from typing import List, Dict, Optional, Set
from .base import BaseKeywordRegistry


class KeywordRegistry(BaseKeywordRegistry):
    """
    Registry for managing keywords by category and complaint type.
    
    This allows different complaint types (housing, employment, consumer protection)
    to have their own keyword sets while sharing common keywords.
    
    Example:
        >>> registry = KeywordRegistry()
        >>> registry.register_keywords('complaint', ['fraud', 'deception'], 
        ...                            complaint_type='consumer')
        >>> keywords = registry.get_keywords('complaint', complaint_type='consumer')
    """
    
    def __init__(self):
        """Initialize the keyword registry."""
        # Structure: {category: {complaint_type: [keywords]}}
        # complaint_type=None means global keywords
        self._registry: Dict[str, Dict[Optional[str], Set[str]]] = {}
    
    def register_keywords(self, category: str, keywords: List[str], 
                         complaint_type: Optional[str] = None) -> None:
        """
        Register keywords for a category.
        
        Args:
            category: Category name (e.g., 'complaint', 'evidence', 'legal')
            keywords: List of keywords to register
            complaint_type: Optional complaint type to scope keywords to
        """
        if category not in self._registry:
            self._registry[category] = {}
        
        if complaint_type not in self._registry[category]:
            self._registry[category][complaint_type] = set()
        
        self._registry[category][complaint_type].update(keywords)
    
    def get_keywords(self, category: str, 
                     complaint_type: Optional[str] = None) -> List[str]:
        """
        Get keywords for a category.
        
        Args:
            category: Category name
            complaint_type: Optional complaint type to filter by
            
        Returns:
            List of keywords (includes global + type-specific if type is specified)
        """
        if category not in self._registry:
            return []
        
        keywords = set()
        
        # Always include global keywords (complaint_type=None)
        if None in self._registry[category]:
            keywords.update(self._registry[category][None])
        
        # Add type-specific keywords if requested
        if complaint_type and complaint_type in self._registry[category]:
            keywords.update(self._registry[category][complaint_type])
        
        return sorted(list(keywords))
    
    def get_type_specific_keywords(self, category: str, 
                                   complaint_type: str) -> List[str]:
        """
        Get only type-specific keywords (excluding global keywords).
        
        Useful for applicability tagging to avoid false positives from
        global keywords that appear in all complaint types.
        
        Args:
            category: Category name
            complaint_type: Complaint type
            
        Returns:
            List of type-specific keywords only
        """
        if category not in self._registry:
            return []
        
        if complaint_type not in self._registry[category]:
            return []
        
        return sorted(list(self._registry[category][complaint_type]))
    
    def get_all_categories(self, complaint_type: Optional[str] = None) -> List[str]:
        """
        Get all registered categories.
        
        Args:
            complaint_type: Optional complaint type to filter by
            
        Returns:
            List of category names
        """
        if complaint_type is None:
            return list(self._registry.keys())
        else:
            # Only return categories that have keywords for this type
            return [cat for cat in self._registry.keys() 
                    if complaint_type in self._registry[cat]]
    
    def get_complaint_types(self, category: Optional[str] = None) -> List[str]:
        """
        Get all registered complaint types.
        
        Args:
            category: Optional category to filter by
            
        Returns:
            List of complaint type names
        """
        types = set()
        
        if category:
            if category in self._registry:
                types.update(t for t in self._registry[category].keys() if t is not None)
        else:
            for category_types in self._registry.values():
                types.update(t for t in category_types.keys() if t is not None)
        
        return sorted(list(types))
    
    # ============================================================================
    # Batch 214: KeywordRegistry Analysis Methods
    # ============================================================================
    
    def total_categories(self) -> int:
        """Return the total number of registered categories.
        
        Returns:
            Count of categories in the registry.
        """
        return len(self._registry)
    
    def total_keywords_in_category(self, category: str) -> int:
        """Count all keywords in a category (global + type-specific).
        
        Args:
            category: Category name.
            
        Returns:
            Total number of unique keywords in this category.
        """
        if category not in self._registry:
            return 0
        
        all_keywords = set()
        for keywords_set in self._registry[category].values():
            all_keywords.update(keywords_set)
        return len(all_keywords)
    
    def category_with_most_keywords(self) -> str:
        """Find the category with the most keywords.
        
        Returns:
            Category name with most keywords, or 'none' if no categories.
        """
        if not self._registry:
            return 'none'
        
        max_category = None
        max_count = 0
        for category in self._registry:
            count = self.total_keywords_in_category(category)
            if count > max_count:
                max_count = count
                max_category = category
        
        return max_category if max_category else 'none'
    
    def keywords_by_type(self, complaint_type: str) -> Dict[str, int]:
        """Get keyword counts for a specific complaint type across all categories.
        
        Args:
            complaint_type: The complaint type to analyze.
            
        Returns:
            Dict mapping category names to keyword counts for this type.
        """
        result = {}
        for category in self._registry:
            if complaint_type in self._registry[category]:
                result[category] = len(self._registry[category][complaint_type])
        return result
    
    def global_keywords_count(self) -> int:
        """Count total number of global keywords (not type-specific) across all categories.
        
        Returns:
            Number of global keywords.
        """
        count = 0
        for category_data in self._registry.values():
            if None in category_data:
                count += len(category_data[None])
        return count
    
    def type_specific_keywords_count(self) -> int:
        """Count total number of type-specific keywords across all categories.
        
        Returns:
            Number of type-specific keywords.
        """
        count = 0
        for category_data in self._registry.values():
            for complaint_type, keywords_set in category_data.items():
                if complaint_type is not None:
                    count += len(keywords_set)
        return count
    
    def has_keywords_for_type(self, complaint_type: str) -> bool:
        """Check if any category has keywords registered for a complaint type.
        
        Args:
            complaint_type: The complaint type to check.
            
        Returns:
            True if any keywords exist for this type, False otherwise.
        """
        for category_data in self._registry.values():
            if complaint_type in category_data:
                return True
        return False
    
    def average_keywords_per_category(self) -> float:
        """Calculate the average number of keywords per category.
        
        Returns:
            Mean keyword count per category, or 0.0 if no categories.
        """
        if not self._registry:
            return 0.0
        
        total = sum(self.total_keywords_in_category(cat) for cat in self._registry)
        return total / len(self._registry)
    
    def categories_with_type_specific_keywords(self) -> int:
        """Count how many categories have type-specific keywords (not just global).
        
        Returns:
            Number of categories with at least one type-specific keyword set.
        """
        count = 0
        for category_data in self._registry.values():
            has_type_specific = any(t is not None for t in category_data.keys())
            if has_type_specific:
                count += 1
        return count
    
    def keyword_coverage_ratio(self) -> float:
        """Calculate ratio of type-specific to total keywords.
        
        Returns:
            Ratio (0.0 to 1.0) of type-specific keywords to all keywords.
        """
        total = self.global_keywords_count() + self.type_specific_keywords_count()
        if total == 0:
            return 0.0
        return self.type_specific_keywords_count() / total


# Create global registry instance
_global_registry = KeywordRegistry()


# Convenience functions for global registry
def register_keywords(category: str, keywords: List[str], 
                     complaint_type: Optional[str] = None) -> None:
    """Register keywords in the global registry."""
    _global_registry.register_keywords(category, keywords, complaint_type)


def get_keywords(category: str, complaint_type: Optional[str] = None) -> List[str]:
    """Get keywords from the global registry."""
    return _global_registry.get_keywords(category, complaint_type)


def get_type_specific_keywords(category: str, complaint_type: str) -> List[str]:
    """
    Get only type-specific keywords (excluding global keywords) from the global registry.
    
    Useful for applicability tagging to avoid false positives.
    """
    return _global_registry.get_type_specific_keywords(category, complaint_type)


# Register default keywords (complaint_type=None means global)
register_keywords('complaint', [
    # Discrimination types
    'discrimination', 'discriminate', 'discriminatory',
    'harassment', 'hostile environment',
    'retaliation', 'retaliate', 'retaliatory',
    
    # Protected classes (universal)
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
    
    # Civil rights
    'civil rights', 'equal protection', 'due process',
    'constitutional rights', 'constitutional violation',
    
    # Complaint process
    'complainant', 'respondent', 'charging party',
    'aggrieved person', 'complaint', 'charge',
])

# Housing-specific keywords
register_keywords('complaint', [
    'fair housing', 'housing discrimination',
    'reasonable accommodation', 'reasonable modification',
    'familial status', 'source of income',
    'section 8', 'housing choice voucher',
    'public housing', 'affordable housing',
    'tenant', 'landlord', 'lease', 'rental',
    'eviction', 'housing authority',
], complaint_type='housing')

# Employment-specific keywords
register_keywords('complaint', [
    'employment discrimination', 'workplace discrimination',
    'equal employment opportunity', 'eeoc',
    'title vii', 'ada', 'adea', 'fmla',
    'wrongful termination', 'hostile work environment',
], complaint_type='employment')

# Evidence keywords (universal)
register_keywords('evidence', [
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
])

# Legal authority keywords (universal)
register_keywords('legal', [
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
])

# Binding/enforceable indicators
register_keywords('binding', [
    'policy', 'ordinance', 'statewide', 'model policy',
    'contract', 'agreement', 'standard',
    'required', 'must', 'shall', 'mandatory',
    'applicable to', 'applicability', 'enforceable',
    'governing', 'binding', 'regulation', 'rule',
    'directive', 'compliance', 'obligated', 'stipulation',
])

# Severity keywords
register_keywords('severity_high', [
    'systemic', 'pattern', 'practice',
    'intentional', 'willful', 'deliberate',
    'egregious', 'severe', 'pervasive',
    'ongoing', 'repeated', 'continuous',
    'punitive damages', 'injunctive relief',
])

register_keywords('severity_medium', [
    'violation', 'breach', 'failure',
    'inadequate', 'insufficient',
    'disparate impact', 'adverse effect',
    'compensatory damages',
])

register_keywords('severity_low', [
    'potential', 'possible', 'may',
    'unintentional', 'inadvertent',
    'technical', 'procedural',
    'correctable', 'remediable',
])


# Backward compatibility: export as constants
COMPLAINT_KEYWORDS = get_keywords('complaint')
EVIDENCE_KEYWORDS = get_keywords('evidence')
LEGAL_AUTHORITY_KEYWORDS = get_keywords('legal')
BINDING_KEYWORDS = get_keywords('binding')


def _get_applicability_keywords() -> Dict[str, List[str]]:
    """
    Get applicability keywords dynamically.
    
    This function is lazy-loaded to ensure DEI complaint type is registered
    before keywords are retrieved.
    """
    return {
        'housing': get_keywords('applicability_housing', complaint_type='dei'),
        'employment': get_keywords(
            'applicability_employment', complaint_type='dei'
        ),
        'public_accommodation': get_keywords(
            'applicability_public_accommodation', complaint_type='dei'
        ),
        'lending': get_keywords('applicability_lending', complaint_type='dei'),
        'education': get_keywords('applicability_education', complaint_type='dei'),
        'government_services': get_keywords(
            'applicability_government_services', complaint_type='dei'
        ),
        'procurement': get_keywords(
            'applicability_procurement', complaint_type='dei'
        ),
        'training': get_keywords('applicability_training', complaint_type='dei'),
        'community_engagement': get_keywords(
            'applicability_community_engagement', complaint_type='dei'
        ),
    }


# Lazy-loaded property for backward compatibility
class _ApplicabilityKeywords:
    """
    Lazy-loaded applicability keywords for backward compatibility.
    
    This class implements a dictionary-like interface that lazily loads
    DEI applicability keywords on first access, with thread-safe initialization.
    """
    
    def __init__(self):
        """Initialize with thread-safe lazy loading."""
        import threading
        self._lock = threading.Lock()
        self._cache = None
    
    def _ensure_loaded(self):
        """Ensure the cache is loaded (thread-safe)."""
        if self._cache is None:
            with self._lock:
                # Double-check pattern to avoid race conditions
                if self._cache is None:
                    self._cache = _get_applicability_keywords()
    
    def __getitem__(self, key):
        self._ensure_loaded()
        return self._cache[key]
    
    def __contains__(self, key):
        self._ensure_loaded()
        return key in self._cache
    
    def keys(self):
        self._ensure_loaded()
        return self._cache.keys()
    
    def values(self):
        self._ensure_loaded()
        return self._cache.values()
    
    def items(self):
        self._ensure_loaded()
        return self._cache.items()
    
    def get(self, key, default=None):
        self._ensure_loaded()
        return self._cache.get(key, default)
    
    def __len__(self):
        self._ensure_loaded()
        return len(self._cache)
    
    def __iter__(self):
        self._ensure_loaded()
        return iter(self._cache)
    
    def __repr__(self):
        self._ensure_loaded()
        return repr(self._cache)


# Backward compatibility: lazy-loaded APPLICABILITY_KEYWORDS
APPLICABILITY_KEYWORDS = _ApplicabilityKeywords()
