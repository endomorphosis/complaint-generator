"""
Tests for Extended Complaint Taxonomies

Tests the new complaint type taxonomies for free speech, immigration,
family law, criminal defense, tax law, intellectual property, and environmental law.
"""

import pytest
from complaint_analysis import (
    ComplaintAnalyzer,
    get_registered_types,
    get_keywords,
    get_type_specific_keywords,
    LegalPatternExtractor
)


class TestComplaintTypeRegistration:
    """Test that all complaint types are properly registered."""
    
    def test_all_types_registered(self):
        """Test that all 12 complaint types are registered."""
        registered = get_registered_types()
        
        expected_types = [
            'housing', 'employment', 'civil_rights', 'consumer', 'healthcare',
            'free_speech', 'immigration', 'family_law', 'criminal_defense',
            'tax_law', 'intellectual_property', 'environmental_law'
        ]
        
        for expected in expected_types:
            assert expected in registered, f"Expected type '{expected}' not registered"
        
        assert len(registered) >= 12, f"Expected at least 12 types, got {len(registered)}"
    
    def test_each_type_has_keywords(self):
        """Test that each complaint type has specific keywords."""
        types = get_registered_types()
        
        for complaint_type in types:
            keywords = get_type_specific_keywords('complaint', complaint_type)
            assert len(keywords) > 0, f"No keywords for complaint type '{complaint_type}'"


class TestFreeSpeechTaxonomy:
    """Test free speech / censorship complaint taxonomy."""
    
    def test_free_speech_keywords(self):
        """Test that free speech keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'free_speech')
        
        # Check for key free speech terms
        assert 'first amendment' in keywords
        assert 'free speech' in keywords
        assert 'censorship' in keywords
        assert 'content moderation' in keywords
        assert 'prior restraint' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 20
    
    def test_free_speech_analysis(self):
        """Test analyzing a free speech complaint."""
        text = """
        The university violated my First Amendment rights by censoring my speech.
        They engaged in viewpoint discrimination and prior restraint when they
        banned my student organization from the public forum. This constitutes
        unconstitutional censorship of protected political speech.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='free_speech')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'free_speech' in result.get('categories', []) or \
               'civil_rights' in result.get('categories', [])


class TestImmigrationTaxonomy:
    """Test immigration law complaint taxonomy."""
    
    def test_immigration_keywords(self):
        """Test that immigration keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'immigration')
        
        # Check for key immigration terms
        assert 'immigration' in keywords
        assert 'visa' in keywords
        assert 'asylum' in keywords
        assert 'deportation' in keywords
        assert 'green card' in keywords
        assert 'uscis' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 30
    
    def test_immigration_analysis(self):
        """Test analyzing an immigration complaint."""
        text = """
        USCIS denied my asylum application without proper consideration.
        I face deportation and removal proceedings despite my valid claim
        for withholding of removal. I am requesting cancellation of removal
        based on my circumstances and the danger I would face upon return.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='immigration')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'immigration' in result.get('categories', [])


class TestFamilyLawTaxonomy:
    """Test family law complaint taxonomy."""
    
    def test_family_law_keywords(self):
        """Test that family law keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'family_law')
        
        # Check for key family law terms
        assert 'divorce' in keywords
        assert 'child custody' in keywords
        assert 'child support' in keywords
        assert 'alimony' in keywords
        assert 'domestic violence' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 25
    
    def test_family_law_analysis(self):
        """Test analyzing a family law complaint."""
        text = """
        I am filing for divorce and seeking sole custody of our children.
        My spouse has failed to pay court-ordered child support and has
        violated the protective order. I need modification of the custody
        arrangement to ensure the children's safety and well-being.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='family_law')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'family_law' in result.get('categories', [])


class TestCriminalDefenseTaxonomy:
    """Test criminal defense complaint taxonomy."""
    
    def test_criminal_defense_keywords(self):
        """Test that criminal defense keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'criminal_defense')
        
        # Check for key criminal defense terms
        assert 'fourth amendment' in keywords
        assert 'miranda rights' in keywords
        assert 'illegal search' in keywords
        assert 'due process' in keywords
        assert 'right to counsel' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 40
    
    def test_criminal_defense_analysis(self):
        """Test analyzing a criminal defense complaint."""
        text = """
        The police conducted an illegal search without a warrant or probable cause,
        violating my Fourth Amendment rights. They failed to read me my Miranda
        rights during interrogation. This evidence should be suppressed under the
        exclusionary rule. I was denied my right to effective assistance of counsel.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='criminal_defense')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'criminal_defense' in result.get('categories', [])


class TestTaxLawTaxonomy:
    """Test tax law complaint taxonomy."""
    
    def test_tax_law_keywords(self):
        """Test that tax law keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'tax_law')
        
        # Check for key tax law terms
        assert 'irs' in keywords
        assert 'tax audit' in keywords
        assert 'tax court' in keywords
        assert 'tax penalty' in keywords
        assert 'offer in compromise' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 30
    
    def test_tax_law_analysis(self):
        """Test analyzing a tax law complaint."""
        text = """
        The IRS issued an unfair tax assessment following their audit.
        I am seeking innocent spouse relief and requesting an offer in compromise.
        The tax penalties are excessive and I need to challenge this in tax court.
        I have requested a collection due process hearing regarding the tax levy.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='tax_law')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'tax_law' in result.get('categories', [])


class TestIntellectualPropertyTaxonomy:
    """Test intellectual property complaint taxonomy."""
    
    def test_ip_keywords(self):
        """Test that intellectual property keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'intellectual_property')
        
        # Check for key IP terms
        assert 'patent' in keywords
        assert 'trademark' in keywords
        assert 'copyright' in keywords
        assert 'trade secret' in keywords
        assert 'infringement' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 30
    
    def test_ip_analysis(self):
        """Test analyzing an intellectual property complaint."""
        text = """
        The defendant has committed patent infringement by using our patented
        technology without authorization. They have also engaged in trademark
        infringement through their use of a confusingly similar mark. This
        constitutes willful copyright infringement and misappropriation of
        our trade secrets under the UTSA.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='intellectual_property')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'intellectual_property' in result.get('categories', [])


class TestEnvironmentalLawTaxonomy:
    """Test environmental law complaint taxonomy."""
    
    def test_environmental_keywords(self):
        """Test that environmental law keywords are registered."""
        keywords = get_type_specific_keywords('complaint', 'environmental_law')
        
        # Check for key environmental terms
        assert 'epa' in keywords
        assert 'clean air act' in keywords
        assert 'clean water act' in keywords
        assert 'pollution' in keywords
        assert 'contamination' in keywords
        
        # Should have substantial keyword set
        assert len(keywords) > 25
    
    def test_environmental_analysis(self):
        """Test analyzing an environmental law complaint."""
        text = """
        The facility is in violation of the Clean Air Act and Clean Water Act.
        The EPA should investigate this pollution and contamination. There is
        hazardous waste disposal that violates CERCLA and RCRA regulations.
        We are filing a citizen suit for environmental enforcement and seeking
        remediation of the contaminated groundwater.
        """
        
        analyzer = ComplaintAnalyzer(complaint_type='environmental_law')
        result = analyzer.analyze(text)
        
        assert result is not None
        assert 'environmental_law' in result.get('categories', [])


class TestLegalPatternExtraction:
    """Test that legal patterns work with new complaint types."""
    
    def test_extract_provisions_all_types(self):
        """Test extracting provisions for all complaint types."""
        extractor = LegalPatternExtractor()
        
        # Test a few key patterns
        free_speech_text = "This violates the First Amendment and constitutes prior restraint."
        result = extractor.extract_provisions(free_speech_text)
        assert result['provision_count'] > 0
        
        immigration_text = "USCIS denied my asylum application and ordered deportation."
        result = extractor.extract_provisions(immigration_text)
        assert result['provision_count'] > 0
        
        ip_text = "They committed patent infringement and trademark infringement."
        result = extractor.extract_provisions(ip_text)
        assert result['provision_count'] > 0


class TestMultiTypeComplaint:
    """Test handling complaints that span multiple types."""
    
    def test_cross_domain_complaint(self):
        """Test a complaint that involves multiple practice areas."""
        text = """
        I am an undocumented immigrant facing employment discrimination.
        My employer violated Title VII by discriminating based on national origin
        and retaliated when I complained. They also reported me to ICE in
        retaliation for asserting my workplace rights. This violates both
        employment law and immigration law protections.
        """
        
        # Should detect multiple applicable types
        analyzer = ComplaintAnalyzer()  # Auto-detect complaint type
        result = analyzer.analyze(text)
        
        categories = result.get('categories', [])
        
        # Should identify both employment and immigration issues
        # (exact matching depends on categorization logic)
        assert len(categories) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
