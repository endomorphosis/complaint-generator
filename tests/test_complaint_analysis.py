"""
Tests for the complaint_analysis module.

Validates legal pattern extraction, complaint risk scoring, and related keyword
configuration used by the complaint_analysis utilities.
"""

import pytest
from complaint_analysis import (
    LegalPatternExtractor,
    ComplaintRiskScorer,
    COMPLAINT_KEYWORDS,
    EVIDENCE_KEYWORDS,
    LEGAL_AUTHORITY_KEYWORDS,
    APPLICABILITY_KEYWORDS
)


# Sample test data
SAMPLE_FAIR_HOUSING_TEXT = """
This is a complaint regarding fair housing discrimination. The landlord refused 
to provide a reasonable accommodation for my disability. I requested a service 
animal as a reasonable accommodation under the Fair Housing Act (42 U.S.C. § 3604). 
The landlord's actions constitute discrimination based on disability, which is a 
protected class under federal law. I am seeking injunctive relief and compensatory 
damages for this violation of my civil rights.
"""

SAMPLE_EMPLOYMENT_TEXT = """
I am filing a complaint for employment discrimination under Title VII. My employer 
engaged in harassment and created a hostile work environment. This constitutes 
intentional discrimination based on sex, which violates the Equal Employment 
Opportunity Act. I have documentation and witness testimony as evidence. The EEOC 
should investigate this matter and provide appropriate remedies.
"""

SAMPLE_LOW_RISK_TEXT = """
This is a general inquiry about housing policies. I would like to understand 
the application process for affordable housing programs. Can you provide 
information about eligibility requirements and the timeline for approval?
"""


class TestLegalPatternExtractor:
    """Test legal pattern extraction functionality."""
    
    def test_extract_provisions_housing(self):
        """Test extracting legal provisions from housing complaint."""
        extractor = LegalPatternExtractor()
        result = extractor.extract_provisions(SAMPLE_FAIR_HOUSING_TEXT)
        
        assert result['provision_count'] > 0
        assert 'fair housing' in [t.lower() for t in result['terms_found']]
        assert 'reasonable accommodation' in [t.lower() for t in result['terms_found']]
        assert 'disability' in [t.lower() for t in result['terms_found']]
        assert len(result['provisions']) > 0
    
    def test_extract_provisions_employment(self):
        """Test extracting legal provisions from employment complaint."""
        extractor = LegalPatternExtractor()
        result = extractor.extract_provisions(SAMPLE_EMPLOYMENT_TEXT)
        
        assert result['provision_count'] > 0
        assert 'title vii' in [t.lower() for t in result['terms_found']]
        assert 'discrimination' in [t.lower() for t in result['terms_found']]
        assert 'harassment' in [t.lower() for t in result['terms_found']]
    
    def test_extract_citations(self):
        """Test extracting legal citations."""
        extractor = LegalPatternExtractor()
        citations = extractor.extract_citations(SAMPLE_FAIR_HOUSING_TEXT)
        
        assert len(citations) > 0
        assert any('42 U.S.C' in c['citation'] for c in citations)
        assert any(c['type'] == 'federal_statute' for c in citations)
    
    def test_categorize_complaint_housing(self):
        """Test categorizing housing complaint."""
        extractor = LegalPatternExtractor()
        categories = extractor.categorize_complaint_type(SAMPLE_FAIR_HOUSING_TEXT)
        
        assert 'housing' in categories
        assert 'disability' in categories
        assert 'discrimination' in categories
    
    def test_categorize_complaint_employment(self):
        """Test categorizing employment complaint."""
        extractor = LegalPatternExtractor()
        categories = extractor.categorize_complaint_type(SAMPLE_EMPLOYMENT_TEXT)
        
        assert 'employment' in categories
        assert 'discrimination' in categories
        assert 'harassment' in categories
    
    def test_find_protected_classes(self):
        """Test finding protected classes."""
        extractor = LegalPatternExtractor()
        
        housing_classes = extractor.find_protected_classes(SAMPLE_FAIR_HOUSING_TEXT)
        assert 'disability' in housing_classes
        
        employment_classes = extractor.find_protected_classes(SAMPLE_EMPLOYMENT_TEXT)
        assert 'sex' in employment_classes
    
    def test_custom_patterns(self):
        """Test adding custom patterns."""
        custom_patterns = [r'\b(custom term)\b', r'\b(special keyword)\b']
        extractor = LegalPatternExtractor(custom_patterns=custom_patterns)
        
        text = "This document contains a custom term and special keyword."
        result = extractor.extract_provisions(text)
        
        assert result['provision_count'] >= 2
        assert 'custom term' in [t.lower() for t in result['terms_found']]


class TestRiskScorer:
    """Test risk scoring functionality."""
    
    def test_high_risk_complaint(self):
        """Test high risk complaint scoring."""
        scorer = ComplaintRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_FAIR_HOUSING_TEXT)
        
        assert risk['score'] >= 2  # At least medium risk
        assert risk['level'] in ['medium', 'high']
        assert len(risk['factors']) > 0
        assert len(risk['recommendations']) > 0
    
    def test_medium_risk_complaint(self):
        """Test medium risk complaint scoring."""
        scorer = ComplaintRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_EMPLOYMENT_TEXT)
        
        assert risk['score'] >= 1  # At least low risk
        assert len(risk['factors']) > 0
    
    def test_low_risk_text(self):
        """Test low risk text scoring."""
        scorer = ComplaintRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_LOW_RISK_TEXT)
        
        assert risk['score'] <= 1  # At most low risk
        assert risk['level'] in ['minimal', 'low']
    
    def test_is_actionable(self):
        """Test actionable determination."""
        scorer = ComplaintRiskScorer()
        
        # High/medium risk should be actionable
        assert scorer.is_actionable(SAMPLE_FAIR_HOUSING_TEXT, threshold=2)
        
        # Low risk should not be actionable
        assert not scorer.is_actionable(SAMPLE_LOW_RISK_TEXT, threshold=2)
    
    def test_categorize_severity(self):
        """Test severity categorization."""
        scorer = ComplaintRiskScorer()
        
        housing_severity = scorer.categorize_severity(SAMPLE_FAIR_HOUSING_TEXT)
        assert housing_severity in ['minimal', 'low', 'medium', 'high']
        
        low_risk_severity = scorer.categorize_severity(SAMPLE_LOW_RISK_TEXT)
        assert low_risk_severity in ['minimal', 'low']


class TestKeywords:
    """Test keyword functionality."""
    
    def test_complaint_keywords_exist(self):
        """Test that complaint keywords are defined."""
        assert len(COMPLAINT_KEYWORDS) > 0
        assert 'discrimination' in COMPLAINT_KEYWORDS
        assert 'harassment' in COMPLAINT_KEYWORDS
        assert 'retaliation' in COMPLAINT_KEYWORDS
    
    def test_evidence_keywords_exist(self):
        """Test that evidence keywords are defined."""
        assert len(EVIDENCE_KEYWORDS) > 0
        assert 'witness' in EVIDENCE_KEYWORDS
        assert 'testimony' in EVIDENCE_KEYWORDS
        assert 'document' in EVIDENCE_KEYWORDS
    
    def test_legal_authority_keywords_exist(self):
        """Test that legal authority keywords are defined."""
        assert len(LEGAL_AUTHORITY_KEYWORDS) > 0
        assert 'statute' in LEGAL_AUTHORITY_KEYWORDS
        assert 'regulation' in LEGAL_AUTHORITY_KEYWORDS
    
    def test_applicability_keywords_exist(self):
        """Test that applicability keywords are defined."""
        assert 'housing' in APPLICABILITY_KEYWORDS
        assert 'employment' in APPLICABILITY_KEYWORDS
        assert len(APPLICABILITY_KEYWORDS['housing']) > 0
        assert 'tenant' in APPLICABILITY_KEYWORDS['housing']


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_full_analysis_pipeline(self):
        """Test complete analysis pipeline."""
        extractor = LegalPatternExtractor()
        scorer = ComplaintRiskScorer()
        
        # Extract legal provisions
        provisions = extractor.extract_provisions(SAMPLE_FAIR_HOUSING_TEXT)
        assert provisions['provision_count'] > 0
        
        # Calculate risk with provisions
        risk = scorer.calculate_risk(SAMPLE_FAIR_HOUSING_TEXT, provisions['provisions'])
        assert risk['score'] > 0
        
        # Categorize
        categories = extractor.categorize_complaint_type(SAMPLE_FAIR_HOUSING_TEXT)
        assert len(categories) > 0
        
        # Find protected classes
        protected_classes = extractor.find_protected_classes(SAMPLE_FAIR_HOUSING_TEXT)
        assert len(protected_classes) > 0
    
    def test_multiple_complaint_types(self):
        """Test analyzing different complaint types."""
        extractor = LegalPatternExtractor()
        
        housing_categories = extractor.categorize_complaint_type(SAMPLE_FAIR_HOUSING_TEXT)
        employment_categories = extractor.categorize_complaint_type(SAMPLE_EMPLOYMENT_TEXT)
        
        assert 'housing' in housing_categories
        assert 'employment' in employment_categories
        assert housing_categories != employment_categories


@pytest.mark.integration
class TestHybridIndexer:
    """Test hybrid indexer (requires ipfs_datasets_py)."""
    
    @pytest.mark.asyncio
    async def test_index_document_without_embeddings(self):
        """Test indexing without embeddings (should still work)."""
        from complaint_analysis import HybridDocumentIndexer
        
        indexer = HybridDocumentIndexer(enable_embeddings=False)
        result = await indexer.index_document(SAMPLE_FAIR_HOUSING_TEXT)
        
        assert 'keywords' in result
        assert 'legal_provisions' in result
        assert 'risk_score' in result
        assert 'risk_level' in result
        assert 'applicability' in result
        assert 'relevance_score' in result
    
    @pytest.mark.asyncio  
    async def test_index_document_metadata(self):
        """Test indexing with metadata."""
        from complaint_analysis import HybridDocumentIndexer
        
        indexer = HybridDocumentIndexer(enable_embeddings=False)
        metadata = {'source': 'complaint_form', 'user_id': '123'}
        result = await indexer.index_document(SAMPLE_FAIR_HOUSING_TEXT, metadata)
        
        assert result['metadata'] == metadata
        assert 'indexed_date' in result
    
    def test_get_statistics(self):
        """Test statistics generation."""
        from complaint_analysis import HybridDocumentIndexer
        
        indexer = HybridDocumentIndexer(enable_embeddings=False)
        
        # Create mock indexed documents
        documents = [
            {'risk_level': 'high', 'applicability': ['housing'], 
             'legal_provisions': {'provision_count': 5}, 'relevance_score': 0.8},
            {'risk_level': 'medium', 'applicability': ['employment'], 
             'legal_provisions': {'provision_count': 3}, 'relevance_score': 0.6},
            {'risk_level': 'low', 'applicability': ['housing', 'employment'], 
             'legal_provisions': {'provision_count': 1}, 'relevance_score': 0.3},
        ]
        
        stats = indexer.get_statistics(documents)
        
        assert stats['total'] == 3
        assert stats['risk_distribution']['high'] == 1
        assert stats['risk_distribution']['medium'] == 1
        assert stats['risk_distribution']['low'] == 1
        assert 'housing' in stats['applicability']
        assert 'employment' in stats['applicability']
        assert stats['avg_provisions'] == 3.0
        assert 0 < stats['avg_relevance'] < 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
