"""
Tests for DEI Analysis Components

Tests the DEI-specific functionality integrated from HACC repository:
- DEI risk scoring algorithm
- DEI provision extraction
- Enhanced DEI keywords and taxonomy
"""

import pytest
from complaint_analysis import (
    DEIRiskScorer,
    DEIProvisionExtractor,
    get_keywords,
    APPLICABILITY_KEYWORDS
)


# Sample test data
SAMPLE_DEI_POLICY = """
Section 1. Diversity and Inclusion Requirements

All contractors shall implement diversity, equity, and inclusion initiatives
targeting underserved communities. Contractors must demonstrate cultural
competence and lived experience working with BIPOC populations.

Section 2. Procurement Standards

Awards shall prioritize minority-owned business enterprises (MBE) and
women-owned business enterprises (WBE). This policy is mandatory and
enforceable through contract compliance mechanisms.
"""

SAMPLE_NEUTRAL_POLICY = """
Contractors shall provide services according to professional standards.
All work must meet quality specifications and be completed on time.
Payment terms are net 30 days.
"""

SAMPLE_ASPIRATIONAL_POLICY = """
The agency values diversity and encourages outreach to various communities.
We appreciate vendors who demonstrate cultural awareness.
"""


class TestDEIRiskScorer:
    """Test DEI-specific risk scoring algorithm."""
    
    def test_high_risk_policy(self):
        """Test high-risk policy with DEI + proxy + binding language."""
        scorer = DEIRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_DEI_POLICY)
        
        assert risk['score'] == 3
        assert risk['level'] == 'high'
        assert risk['dei_count'] > 0
        assert risk['proxy_count'] > 0
        assert risk['binding_count'] > 0
        assert len(risk['issues']) > 0
        assert len(risk['recommendations']) > 0
    
    def test_neutral_policy(self):
        """Test neutral policy with no DEI language."""
        scorer = DEIRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_NEUTRAL_POLICY)
        
        assert risk['score'] == 0
        assert risk['level'] == 'compliant'
        assert risk['dei_count'] == 0
        assert risk['proxy_count'] == 0
    
    def test_aspirational_policy(self):
        """Test aspirational policy with DEI but no binding language."""
        scorer = DEIRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_ASPIRATIONAL_POLICY)
        
        assert risk['score'] == 1  # Low risk
        assert risk['level'] == 'low'
        assert risk['dei_count'] > 0
        assert risk['binding_count'] == 0
    
    def test_is_problematic(self):
        """Test problematic determination."""
        scorer = DEIRiskScorer()
        
        assert scorer.is_problematic(SAMPLE_DEI_POLICY, threshold=2)
        assert not scorer.is_problematic(SAMPLE_NEUTRAL_POLICY, threshold=2)
        assert not scorer.is_problematic(SAMPLE_ASPIRATIONAL_POLICY, threshold=2)
    
    def test_applicability_tagging(self):
        """Test applicability area tagging."""
        scorer = DEIRiskScorer()
        tags = scorer.tag_applicability(SAMPLE_DEI_POLICY)
        
        assert 'procurement' in tags  # MBE/WBE mentioned
        assert len(tags) > 0
    
    def test_flagged_keywords(self):
        """Test that specific keywords are flagged."""
        scorer = DEIRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_DEI_POLICY)
        
        flagged = risk['flagged_keywords']
        assert 'dei' in flagged
        assert 'proxy' in flagged
        assert 'binding' in flagged
        assert len(flagged['dei']) > 0


class TestDEIProvisionExtractor:
    """Test DEI provision extraction."""
    
    def test_extract_provisions(self):
        """Test extracting provisions from policy text."""
        extractor = DEIProvisionExtractor()
        provisions = extractor.extract_provisions(SAMPLE_DEI_POLICY, document_type='policy')
        
        assert len(provisions) > 0
        assert all('section' in p for p in provisions)
        assert all('dei_terms' in p for p in provisions)
        assert all('is_binding' in p for p in provisions)
    
    def test_binding_detection(self):
        """Test detection of binding vs non-binding provisions."""
        extractor = DEIProvisionExtractor()
        provisions = extractor.extract_provisions(SAMPLE_DEI_POLICY, document_type='policy')
        
        # Should find at least one binding provision
        binding_provs = [p for p in provisions if p['is_binding']]
        assert len(binding_provs) > 0
        
        # Binding provisions should have binding terms
        for prov in binding_provs:
            assert len(prov['binding_terms']) > 0
    
    def test_no_provisions_in_neutral_text(self):
        """Test that neutral text yields no DEI provisions."""
        extractor = DEIProvisionExtractor()
        provisions = extractor.extract_provisions(SAMPLE_NEUTRAL_POLICY, document_type='policy')
        
        assert len(provisions) == 0
    
    def test_provision_context(self):
        """Test that provisions include context."""
        extractor = DEIProvisionExtractor()
        provisions = extractor.extract_provisions(SAMPLE_DEI_POLICY, document_type='policy')
        
        for prov in provisions:
            assert 'context' in prov
            assert 'text' in prov
            assert len(prov['context']) > len(prov['text'])
    
    def test_summarize_provisions(self):
        """Test provision summarization."""
        extractor = DEIProvisionExtractor()
        provisions = extractor.extract_provisions(SAMPLE_DEI_POLICY, document_type='policy')
        summary = extractor.summarize_provisions(provisions)
        
        assert 'total' in summary
        assert 'binding' in summary
        assert 'non_binding' in summary
        assert 'most_common_terms' in summary
        assert summary['total'] == len(provisions)


class TestEnhancedDEIKeywords:
    """Test enhanced DEI keywords from HACC integration."""
    
    def test_core_dei_keywords(self):
        """Test core DEI keywords are present."""
        keywords = get_keywords('complaint', complaint_type='dei')
        
        # Core terms from HACC
        assert 'diversity' in keywords
        assert 'equity' in keywords
        assert 'inclusion' in keywords
        assert 'dei' in keywords
        assert 'deia' in keywords
        
        # Justice frameworks
        assert 'racial justice' in keywords
        assert 'social justice' in keywords
        
        # Community descriptors
        assert 'marginalized' in keywords
        assert 'bipoc' in keywords
        assert 'people of color' in keywords
        assert 'underrepresented' in keywords
        assert 'underserved' in keywords
    
    def test_proxy_keywords(self):
        """Test DEI proxy/euphemism keywords."""
        proxy_keywords = get_keywords('dei_proxy', complaint_type='dei')
        
        assert 'cultural competence' in proxy_keywords
        assert 'lived experience' in proxy_keywords
        assert 'diversity statement' in proxy_keywords
        assert 'safe space' in proxy_keywords
        assert 'implicit bias' in proxy_keywords
        assert 'first-generation' in proxy_keywords
    
    def test_procurement_keywords(self):
        """Test procurement-specific DEI keywords."""
        procurement = get_keywords('applicability_procurement', complaint_type='dei')
        
        assert 'disadvantaged business enterprise' in procurement
        assert 'dbe' in procurement
        assert 'minority-owned business' in procurement
        assert 'mbe' in procurement
        assert 'women-owned business' in procurement
        assert 'wbe' in procurement
        assert 'mwesb' in procurement
    
    def test_training_keywords(self):
        """Test training-specific keywords."""
        training = get_keywords('applicability_training', complaint_type='dei')
        
        assert 'training' in training
        assert 'cultural competency training' in training
        assert 'implicit bias training' in training
        assert 'diversity training' in training
    
    def test_community_engagement_keywords(self):
        """Test community engagement keywords."""
        engagement = get_keywords('applicability_community_engagement', complaint_type='dei')
        
        assert 'community engagement' in engagement
        assert 'stakeholder' in engagement
        assert 'outreach' in engagement
        assert 'public input' in engagement
    
    def test_applicability_domains(self):
        """Test that all applicability domains are present."""
        domains = list(APPLICABILITY_KEYWORDS.keys())
        
        assert 'housing' in domains
        assert 'employment' in domains
        assert 'procurement' in domains
        assert 'training' in domains
        assert 'community_engagement' in domains
        assert 'public_accommodation' in domains
        assert 'lending' in domains
        assert 'education' in domains
        assert 'government_services' in domains
        
        # Should have 9 domains total
        assert len(domains) == 9


class TestDEIIntegration:
    """Integration tests for DEI functionality."""
    
    def test_complete_analysis_pipeline(self):
        """Test complete DEI analysis pipeline."""
        # Extract provisions
        extractor = DEIProvisionExtractor()
        provisions = extractor.extract_provisions(SAMPLE_DEI_POLICY, document_type='policy')
        assert len(provisions) > 0
        
        # Calculate risk
        scorer = DEIRiskScorer()
        risk = scorer.calculate_risk(SAMPLE_DEI_POLICY)
        assert risk['score'] > 0
        
        # Tag applicability
        tags = scorer.tag_applicability(SAMPLE_DEI_POLICY)
        assert len(tags) > 0
        
        # Verify consistency
        assert risk['dei_count'] > 0  # Should find DEI terms
        assert len(provisions) > 0  # Should find provisions
    
    def test_risk_correlates_with_provisions(self):
        """Test that risk score correlates with provision count."""
        extractor = DEIProvisionExtractor()
        scorer = DEIRiskScorer()
        
        # High-risk document should have provisions
        risk_high = scorer.calculate_risk(SAMPLE_DEI_POLICY)
        provs_high = extractor.extract_provisions(SAMPLE_DEI_POLICY, document_type='policy')
        assert risk_high['score'] >= 2
        assert len(provs_high) > 0
        
        # Neutral document should have no provisions
        risk_neutral = scorer.calculate_risk(SAMPLE_NEUTRAL_POLICY)
        provs_neutral = extractor.extract_provisions(SAMPLE_NEUTRAL_POLICY, document_type='policy')
        assert risk_neutral['score'] == 0
        assert len(provs_neutral) == 0


class TestDEISpecificRetrieval:
    """Tests for DEI-specific keyword and pattern retrieval."""
    
    def test_get_dei_complaint_keywords(self):
        """Test retrieving DEI complaint keywords."""
        keywords = get_keywords('complaint', complaint_type='dei')
        
        # Verify we get keywords back
        assert len(keywords) > 0
        assert isinstance(keywords, list)
        
        # Verify DEI-specific terms are present
        assert 'diversity' in keywords
        assert 'equity' in keywords
        assert 'inclusion' in keywords
    
    def test_get_dei_proxy_keywords(self):
        """Test retrieving DEI proxy keywords."""
        proxy_keywords = get_keywords('dei_proxy', complaint_type='dei')
        
        assert len(proxy_keywords) > 0
        assert 'cultural competence' in proxy_keywords
        assert 'lived experience' in proxy_keywords
    
    def test_get_dei_applicability_housing(self):
        """Test retrieving DEI housing applicability keywords."""
        housing_keywords = get_keywords('applicability_housing', complaint_type='dei')
        
        assert len(housing_keywords) > 0
        assert 'housing' in housing_keywords
        assert 'tenant' in housing_keywords
    
    def test_get_dei_applicability_procurement(self):
        """Test retrieving DEI procurement applicability keywords."""
        procurement_keywords = get_keywords('applicability_procurement', complaint_type='dei')
        
        assert len(procurement_keywords) > 0
        assert 'procurement' in procurement_keywords
        assert 'dbe' in procurement_keywords or 'disadvantaged business enterprise' in procurement_keywords
    
    def test_dei_legal_patterns_accessible(self):
        """Test that DEI legal patterns are registered and accessible."""
        from complaint_analysis import get_legal_terms
        
        # Get DEI-specific patterns
        dei_patterns = get_legal_terms('dei')
        
        # Verify patterns are registered
        assert len(dei_patterns) > 0
        assert isinstance(dei_patterns, list)
        
        # Verify DEI-unique patterns are present (not duplicates)
        pattern_strings = [p for p in dei_patterns]
        assert any('diversity' in p for p in pattern_strings)
        assert any('equity' in p for p in pattern_strings)
    
    def test_dei_pattern_extraction_works(self):
        """Test that DEI patterns can extract provisions."""
        from complaint_analysis import LegalPatternExtractor
        
        extractor = LegalPatternExtractor()
        
        # Test with DEI-specific text
        dei_text = "This policy promotes diversity, equity, and inclusion through targeted initiatives."
        result = extractor.extract_provisions(dei_text)
        
        # Should find DEI terms
        assert result['provision_count'] > 0
        terms_found = [term.lower() for term in result['terms_found']]
        assert any('diversity' in term or 'equity' in term or 'inclusion' in term for term in terms_found)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
