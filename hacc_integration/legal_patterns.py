"""
Legal Pattern Extraction for Complaints

Adapted from HACC's deep_analysis.py - provides regex patterns for extracting
complaint-relevant legal provisions from text.

This module focuses on:
- Fair housing law
- Employment discrimination
- Civil rights violations
- Protected class references
- Legal remedies and relief
"""

import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# Legal term patterns adapted from HACC for complaint analysis
COMPLAINT_LEGAL_TERMS = [
    # Fair Housing & Discrimination
    r"\b(fair housing)\b",
    r"\b(Fair Housing Act)\b",
    r"\b(FHA)\b",
    r"\b(discrimination)\b",
    r"\b(discriminate|discriminatory)\b",
    r"\b(harassment)\b",
    r"\b(retaliation|retaliate)\b",
    r"\b(hostile environment)\b",
    
    # Reasonable Accommodation
    r"\b(reasonable accommodation)\b",
    r"\b(reasonable modification)\b",
    r"\b(disability accommodation)\b",
    r"\b(auxiliary aids?)\b",
    
    # Protected Classes
    r"\b(protected class(es)?)\b",
    r"\b(familial status)\b",
    r"\b(disability|disabled)\b",
    r"\b(race|racial)\b",
    r"\b(color)\b",
    r"\b(national origin)\b",
    r"\b(religion|religious)\b",
    r"\b(sex|gender)\b",
    r"\b(sexual orientation)\b",
    r"\b(gender identity)\b",
    r"\b(source of income)\b",
    r"\b(marital status)\b",
    
    # Legal Impact
    r"\b(disparate (impact|treatment))\b",
    r"\b(intentional discrimination)\b",
    r"\b(unintentional discrimination)\b",
    r"\b(discriminatory effect)\b",
    r"\b(adverse (impact|effect))\b",
    
    # Housing Specific
    r"\b(Section 8)\b",
    r"\b(Housing Choice Voucher)\b",
    r"\b(public housing)\b",
    r"\b(affordable housing)\b",
    r"\b(tenant|tenancy)\b",
    r"\b(landlord)\b",
    r"\b(lease|rental agreement)\b",
    r"\b(eviction)\b",
    r"\b(housing authority)\b",
    
    # Employment Specific
    r"\b(Title VII)\b",
    r"\b(ADA)\b",
    r"\b(Americans with Disabilities Act)\b",
    r"\b(ADEA)\b",
    r"\b(Age Discrimination in Employment Act)\b",
    r"\b(FMLA)\b",
    r"\b(Family and Medical Leave Act)\b",
    r"\b(EEOC)\b",
    r"\b(Equal Employment Opportunity)\b",
    
    # Federal Law Citations
    r"\b(42 U\.S\.C\.)\b",
    r"\b(29 U\.S\.C\.)\b",
    r"\b(C\.F\.R\.)\b",
    r"\b(Federal Register)\b",
    
    # Remedies & Relief
    r"\b(damages)\b",
    r"\b(compensatory damages)\b",
    r"\b(punitive damages)\b",
    r"\b(injunctive relief)\b",
    r"\b(declaratory relief)\b",
    r"\b(attorney('s)? fees)\b",
    r"\b(equitable relief)\b",
    r"\b(monetary relief)\b",
    
    # Civil Rights
    r"\b(civil rights)\b",
    r"\b(equal protection)\b",
    r"\b(due process)\b",
    r"\b(constitutional (right|violation))\b",
    
    # Complaint-Specific Terms
    r"\b(complainant)\b",
    r"\b(respondent)\b",
    r"\b(charging party)\b",
    r"\b(aggrieved person)\b",
    r"\b(prima facie case)\b",
    r"\b(burden of proof)\b",
    r"\b(preponderance of evidence)\b",
]


class ComplaintLegalPatternExtractor:
    """
    Extract complaint-relevant legal provisions from text.
    
    This class uses regex patterns to identify and extract legal terms,
    statutory citations, and relevant context from documents. It's designed
    to work with ipfs_datasets_py's PDFProcessor and GraphRAG integration.
    
    Example:
        >>> extractor = ComplaintLegalPatternExtractor()
        >>> result = extractor.extract_provisions(document_text)
        >>> for provision in result['provisions']:
        ...     print(f"{provision['term']}: {provision['context'][:100]}")
    """
    
    def __init__(self, custom_patterns: Optional[List[str]] = None):
        """
        Initialize the legal pattern extractor.
        
        Args:
            custom_patterns: Optional additional regex patterns to include
        """
        self.patterns = [re.compile(p, re.IGNORECASE) for p in COMPLAINT_LEGAL_TERMS]
        
        if custom_patterns:
            self.patterns.extend([re.compile(p, re.IGNORECASE) for p in custom_patterns])
    
    def extract_provisions(self, text: str, context_chars: int = 200) -> Dict[str, any]:
        """
        Extract legal provisions with context from text.
        
        Args:
            text: Text to analyze
            context_chars: Number of characters to include before/after match
            
        Returns:
            Dictionary containing:
            - provisions: List of found provisions with context
            - terms_found: Set of unique legal terms found
            - citation_count: Number of legal citations found
            - timestamp: When analysis was performed
        """
        provisions = []
        terms_found = set()
        
        for pattern in self.patterns:
            for match in pattern.finditer(text):
                # Extract context around the match
                start = max(0, match.start() - context_chars)
                end = min(len(text), match.end() + context_chars)
                context = text[start:end]
                
                # Clean up context (remove extra whitespace)
                context = ' '.join(context.split())
                
                term = match.group(0)
                terms_found.add(term.lower())
                
                provisions.append({
                    'term': term,
                    'context': context,
                    'position': match.start(),
                    'pattern': pattern.pattern
                })
        
        # Sort by position in document
        provisions.sort(key=lambda x: x['position'])
        
        return {
            'provisions': provisions,
            'terms_found': list(terms_found),
            'provision_count': len(provisions),
            'unique_terms': len(terms_found),
            'timestamp': datetime.now().isoformat()
        }
    
    def extract_citations(self, text: str) -> List[Dict[str, str]]:
        """
        Extract legal citations (e.g., 42 U.S.C. § 3604).
        
        Args:
            text: Text to analyze
            
        Returns:
            List of found citations with metadata
        """
        citation_patterns = [
            # Federal statutes (e.g., 42 U.S.C. § 3604)
            (r'\b\d+\s+U\.S\.C\.\s+§\s*\d+[a-z]?(?:\(\w+\))?', 'federal_statute'),
            # Code of Federal Regulations (e.g., 24 C.F.R. § 100.70)
            (r'\b\d+\s+C\.F\.R\.\s+§\s*\d+\.\d+', 'cfr'),
            # State statutes (e.g., Cal. Civ. Code § 51)
            (r'\b[A-Z][a-z]+\.\s+[A-Z][a-z]+\.\s+Code\s+§\s*\d+', 'state_statute'),
            # Case citations (simplified)
            (r'\b\d+\s+F\.\s*(?:2d|3d|Supp\.)?\s+\d+', 'federal_case'),
        ]
        
        citations = []
        for pattern, citation_type in citation_patterns:
            regex = re.compile(pattern, re.IGNORECASE)
            for match in regex.finditer(text):
                citations.append({
                    'citation': match.group(0),
                    'type': citation_type,
                    'position': match.start()
                })
        
        return citations
    
    def categorize_complaint_type(self, text: str) -> List[str]:
        """
        Categorize the complaint based on legal terms found.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of applicable complaint categories
        """
        text_lower = text.lower()
        categories = []
        
        # Housing-related
        housing_terms = ['fair housing', 'section 8', 'tenant', 'landlord', 'eviction', 'lease']
        if any(term in text_lower for term in housing_terms):
            categories.append('housing')
        
        # Employment-related
        employment_terms = ['title vii', 'eeoc', 'employment', 'workplace', 'ada']
        if any(term in text_lower for term in employment_terms):
            categories.append('employment')
        
        # Disability
        if 'disability' in text_lower or 'ada' in text_lower or 'reasonable accommodation' in text_lower:
            categories.append('disability')
        
        # Discrimination type
        if 'discrimination' in text_lower or 'discriminate' in text_lower:
            categories.append('discrimination')
        
        # Harassment
        if 'harassment' in text_lower or 'hostile environment' in text_lower:
            categories.append('harassment')
        
        # Retaliation
        if 'retaliation' in text_lower or 'retaliate' in text_lower:
            categories.append('retaliation')
        
        return categories or ['general']
    
    def find_protected_classes(self, text: str) -> List[str]:
        """
        Identify protected classes mentioned in the text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of protected classes found
        """
        protected_classes = {
            'race': ['race', 'racial'],
            'color': ['color'],
            'national_origin': ['national origin', 'nationality'],
            'religion': ['religion', 'religious', 'creed'],
            'sex': ['sex', 'gender'],
            'familial_status': ['familial status', 'family status', 'children'],
            'disability': ['disability', 'disabled', 'handicap'],
            'age': ['age', 'elderly', 'senior'],
            'sexual_orientation': ['sexual orientation', 'lgbt', 'gay', 'lesbian'],
            'gender_identity': ['gender identity', 'transgender'],
            'source_of_income': ['source of income', 'section 8', 'voucher'],
        }
        
        text_lower = text.lower()
        found_classes = []
        
        for class_name, keywords in protected_classes.items():
            if any(keyword in text_lower for keyword in keywords):
                found_classes.append(class_name)
        
        return found_classes
