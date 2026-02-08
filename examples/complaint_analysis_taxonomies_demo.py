#!/usr/bin/env python3
"""
Complaint Analysis Taxonomies Demo

This example demonstrates the extended complaint analysis system with
comprehensive taxonomies for 12 different practice areas.

The complaint_analysis module provides:
- Extensible keyword taxonomies for different complaint types
- Legal pattern extraction across multiple domains
- Risk scoring and categorization
- Easy registration of new complaint types

Practice areas covered:
1. Housing (fair housing, landlord-tenant)
2. Employment (discrimination, workplace rights)
3. Civil Rights (police misconduct, voting rights)
4. Consumer Protection (fraud, deceptive practices)
5. Healthcare (malpractice, HIPAA violations)
6. Free Speech/Censorship (First Amendment, content moderation)
7. Immigration (visa, asylum, deportation)
8. Family Law (divorce, custody, support)
9. Criminal Defense (constitutional rights, due process)
10. Tax Law (IRS disputes, tax court)
11. Intellectual Property (patents, trademarks, copyright)
12. Environmental Law (EPA violations, pollution)
"""

import sys
from pathlib import Path
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from complaint_analysis import (
    ComplaintAnalyzer,
    get_registered_types,
    get_keywords,
    get_type_specific_keywords
)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)


def demo_registered_types():
    """Demonstrate listing all registered complaint types."""
    print_section("Registered Complaint Types")
    
    types = get_registered_types()
    print(f"\nTotal complaint types registered: {len(types)}\n")
    
    for i, complaint_type in enumerate(sorted(types), 1):
        # Get type-specific keywords
        keywords = get_type_specific_keywords('complaint', complaint_type)
        print(f"{i:2d}. {complaint_type:25s} - {len(keywords):3d} keywords")


def demo_keyword_inspection():
    """Demonstrate keyword inspection for different types."""
    print_section("Keyword Taxonomies by Practice Area")
    
    # Sample a few types to show their keywords
    sample_types = ['free_speech', 'immigration', 'family_law', 'criminal_defense']
    
    for complaint_type in sample_types:
        keywords = get_type_specific_keywords('complaint', complaint_type)
        print(f"\n{complaint_type.upper().replace('_', ' ')} ({len(keywords)} keywords):")
        print(f"  Sample: {', '.join(keywords[:8])}...")


def demo_complaint_analysis(complaint_text: str, complaint_type: str = None):
    """Demonstrate analyzing a complaint."""
    print_section(f"Analyzing {complaint_type or 'General'} Complaint")
    
    print("\nComplaint Text:")
    print("-" * 80)
    print(complaint_text.strip())
    print("-" * 80)
    
    # Analyze the complaint
    analyzer = ComplaintAnalyzer(complaint_type=complaint_type)
    result = analyzer.analyze(complaint_text)
    
    print("\nAnalysis Results:")
    print(f"  Categories detected: {', '.join(result['categories'])}")
    print(f"  Risk level: {result['risk_level']} (score: {result['risk_score']})")
    print(f"  Legal provisions found: {result['legal_provisions']['provision_count']}")
    print(f"  Keywords matched: {len(result['keywords_found'])}")
    
    if result['keywords_found']:
        print(f"  Sample keywords: {', '.join(result['keywords_found'][:5])}...")
    
    if result['risk_factors']:
        print(f"\n  Risk factors:")
        for factor in result['risk_factors'][:3]:
            print(f"    - {factor}")
    
    return result


def main():
    """Run all demonstration examples."""
    
    print("\n" + "█"*80)
    print("  COMPLAINT ANALYSIS - COMPREHENSIVE TAXONOMY DEMONSTRATION")
    print("█"*80)
    
    # Demo 1: Show all registered types
    demo_registered_types()
    
    # Demo 2: Show keyword taxonomies
    demo_keyword_inspection()
    
    # Demo 3: Free Speech Complaint
    free_speech_complaint = """
    The university violated my First Amendment rights by censoring my political speech
    at a public forum. They engaged in viewpoint discrimination and prior restraint
    when they banned my student organization from campus. This content moderation policy
    is unconstitutional and creates a chilling effect on protected speech. I am seeking
    injunctive relief to restore my free speech rights.
    """
    demo_complaint_analysis(free_speech_complaint, 'free_speech')
    
    # Demo 4: Immigration Complaint
    immigration_complaint = """
    USCIS denied my asylum application without proper consideration of my persecution
    claim. I now face deportation and removal proceedings despite having a valid basis
    for withholding of removal. My green card application was also denied. I am
    requesting cancellation of removal and adjustment of status based on my
    circumstances. I need immediate help with my immigration case before ICE detains me.
    """
    demo_complaint_analysis(immigration_complaint, 'immigration')
    
    # Demo 5: Family Law Complaint
    family_law_complaint = """
    I am filing for divorce and seeking sole custody of our children due to domestic
    violence. My spouse has violated the protective order multiple times and has
    failed to pay court-ordered child support. I need modification of the custody
    arrangement and enforcement of the support order. I also request spousal support
    (alimony) during this difficult time.
    """
    demo_complaint_analysis(family_law_complaint, 'family_law')
    
    # Demo 6: Criminal Defense Complaint
    criminal_complaint = """
    The police conducted an illegal search of my vehicle without a warrant or probable
    cause, violating my Fourth Amendment rights. They failed to read me my Miranda
    rights during interrogation, and the resulting confession should be suppressed
    under the exclusionary rule. I was denied my Sixth Amendment right to effective
    assistance of counsel. This is a clear violation of due process.
    """
    demo_complaint_analysis(criminal_complaint, 'criminal_defense')
    
    # Demo 7: Intellectual Property Complaint
    ip_complaint = """
    The defendant has committed patent infringement by manufacturing and selling products
    that use our patented technology without authorization. They have also engaged in
    trademark infringement through use of a confusingly similar mark that creates
    likelihood of confusion in the marketplace. Additionally, they committed copyright
    infringement by copying our software and misappropriated our trade secrets in
    violation of the UTSA. We seek injunctive relief and damages.
    """
    demo_complaint_analysis(ip_complaint, 'intellectual_property')
    
    # Demo 8: Environmental Law Complaint
    environmental_complaint = """
    The industrial facility is in violation of the Clean Air Act and Clean Water Act
    through ongoing air pollution and water pollution. The EPA should investigate this
    environmental hazard. There is improper hazardous waste disposal that violates
    CERCLA and RCRA regulations. We are filing a citizen suit for environmental
    enforcement and seeking remediation of the contaminated groundwater and soil.
    This is a Superfund site requiring immediate cleanup.
    """
    demo_complaint_analysis(environmental_complaint, 'environmental_law')
    
    # Demo 9: Tax Law Complaint
    tax_complaint = """
    The IRS issued an unfair tax assessment following their audit of my returns.
    I am seeking innocent spouse relief due to my ex-spouse's fraudulent tax reporting.
    I request an offer in compromise to settle this tax liability. The tax penalties
    and interest are excessive. I need to challenge this in tax court and request a
    collection due process hearing regarding the proposed tax levy on my wages.
    """
    demo_complaint_analysis(tax_complaint, 'tax_law')
    
    # Demo 10: Multi-domain complaint (employment + immigration)
    multi_domain_complaint = """
    I am an undocumented immigrant experiencing employment discrimination at my workplace.
    My employer violated Title VII by discriminating based on my national origin and
    creating a hostile work environment. When I complained to HR, they retaliated by
    reporting me to ICE. This violates both employment law protections and immigration
    law. I fear deportation due to this retaliatory action. I need help with both my
    EEOC complaint and my immigration status.
    """
    demo_complaint_analysis(multi_domain_complaint, None)  # Auto-detect
    
    # Final summary
    print_section("Summary")
    print("\nThe complaint_analysis module successfully provides:")
    print("  ✓ 12 comprehensive complaint type taxonomies")
    print("  ✓ Hundreds of domain-specific keywords")
    print("  ✓ Automated complaint categorization")
    print("  ✓ Risk assessment and scoring")
    print("  ✓ Legal provision extraction")
    print("  ✓ Extensible architecture for new complaint types")
    
    print("\nFor more information, see:")
    print("  - complaint_analysis/README.md")
    print("  - docs/COMPLAINT_ANALYSIS_EXAMPLES.md")
    print("  - tests/test_complaint_taxonomies.py")
    
    print("\n" + "█"*80)
    print("  END OF DEMONSTRATION")
    print("█"*80 + "\n")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
