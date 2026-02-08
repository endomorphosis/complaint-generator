#!/usr/bin/env python3
"""
DEI Taxonomy Example

Demonstrates the DEI (Diversity, Equity, and Inclusion) complaint taxonomy
integrated into the complaint_analysis module. This taxonomy was formerly
part of the hacc_integration module and now exists as a first-class
complaint type in complaint_analysis.

The DEI taxonomy includes:
- Comprehensive discrimination, harassment, and civil rights keywords
- Legal patterns for fair housing, employment, and civil rights violations
- Risk scoring based on severity indicators
- Applicability keywords across multiple domains (housing, employment, etc.)
"""

from complaint_analysis import (
    get_registered_types,
    get_keywords,
    LegalPatternExtractor,
    ComplaintRiskScorer,
    ComplaintAnalyzer
)


def main():
    print("=" * 80)
    print("DEI Taxonomy Example")
    print("=" * 80)
    print()
    
    # Show all registered complaint types
    print("1. Registered Complaint Types:")
    types = get_registered_types()
    print(f"   Total: {len(types)}")
    print(f"   Types: {', '.join(types)}")
    print()
    
    # Show DEI-specific keywords
    print("2. DEI Taxonomy Keywords:")
    print(f"   - Complaint keywords: {len(get_keywords('complaint', complaint_type='dei'))}")
    print(f"   - Evidence keywords: {len(get_keywords('evidence', complaint_type='dei'))}")
    print(f"   - Legal keywords: {len(get_keywords('legal', complaint_type='dei'))}")
    print(f"   - Binding keywords: {len(get_keywords('binding', complaint_type='dei'))}")
    print()
    
    # Show applicability domains
    print("3. DEI Applicability Domains:")
    domains = ['housing', 'employment', 'public_accommodation', 'lending', 
               'education', 'government_services']
    for domain in domains:
        keywords = get_keywords(f'applicability_{domain}', complaint_type='dei')
        print(f"   - {domain}: {len(keywords)} keywords")
    print()
    
    # Analyze a sample complaint
    print("4. Sample DEI Complaint Analysis:")
    print()
    
    sample_complaint = """
    I am filing a complaint regarding housing discrimination. My landlord refused
    to provide a reasonable accommodation for my disability, which is a violation
    of the Fair Housing Act (42 U.S.C. § 3604). I requested a service animal as
    a reasonable accommodation under the ADA, but my request was denied without
    proper justification.
    
    This constitutes intentional discrimination based on disability, which is a
    protected class under federal law. The landlord's actions have created a
    hostile housing environment and have caused me significant distress.
    
    I am seeking injunctive relief, compensatory damages for emotional distress,
    and reasonable attorney's fees as provided under the Fair Housing Act.
    """
    
    print("   Complaint Text:")
    print("   " + "-" * 76)
    for line in sample_complaint.strip().split('\n'):
        print(f"   {line.strip()}")
    print("   " + "-" * 76)
    print()
    
    # Extract legal provisions
    print("5. Legal Pattern Extraction:")
    extractor = LegalPatternExtractor()
    provisions = extractor.extract_provisions(sample_complaint)
    
    print(f"   - Provisions found: {provisions['provision_count']}")
    print(f"   - Unique terms: {provisions['unique_terms']}")
    terms_found = provisions.get('terms_found', [])
    if terms_found:
        print(f"   - Legal terms: {', '.join(terms_found[:10])}")
    else:
        print("   - Legal terms: (none found)")
    print()
    
    # Extract citations
    citations = extractor.extract_citations(sample_complaint)
    if citations:
        print(f"   - Legal citations found:")
        for citation in citations:
            print(f"     • {citation['citation']} ({citation['type']})")
    print()
    
    # Categorize complaint
    categories = extractor.categorize_complaint_type(sample_complaint)
    print(f"   - Complaint categories: {', '.join(categories)}")
    print()
    
    # Find protected classes
    protected_classes = extractor.find_protected_classes(sample_complaint)
    print(f"   - Protected classes: {', '.join(protected_classes)}")
    print()
    
    # Calculate risk score
    print("6. Risk Assessment:")
    scorer = ComplaintRiskScorer()
    risk = scorer.calculate_risk(sample_complaint, provisions['provisions'])
    
    print(f"   - Risk Level: {risk['level'].upper()} (score: {risk['score']}/3)")
    print(f"   - Complaint keywords found: {risk['complaint_keywords']}")
    print(f"   - Binding keywords found: {risk['binding_keywords']}")
    print(f"   - Legal provisions found: {risk['legal_provisions']}")
    print(f"   - Severity indicators: {risk['severity_indicators']}")
    print()
    
    print("   Risk Factors:")
    for factor in risk['factors']:
        print(f"     • {factor}")
    print()
    
    print("   Recommendations:")
    for i, rec in enumerate(risk['recommendations'], 1):
        print(f"     {i}. {rec}")
    print()
    
    # Test backward compatibility
    print("7. Backward Compatibility:")
    print("   The DEI taxonomy maintains full backward compatibility with")
    print("   hacc_integration module. The following imports still work:")
    print()
    print("   from hacc_integration import (")
    print("       ComplaintLegalPatternExtractor,")
    print("       ComplaintRiskScorer,")
    print("       COMPLAINT_KEYWORDS,")
    print("       APPLICABILITY_KEYWORDS")
    print("   )")
    print()
    print("   Note: A deprecation warning will be shown encouraging migration")
    print("   to the complaint_analysis module.")
    print()
    
    print("=" * 80)
    print("Example completed successfully!")
    print("=" * 80)


if __name__ == '__main__':
    main()
