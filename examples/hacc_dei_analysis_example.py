#!/usr/bin/env python3
"""
Complete DEI Policy Analysis Example

Demonstrates the complete HACC-integrated DEI analysis workflow:
1. Risk assessment with DEIRiskScorer
2. Provision extraction with DEIProvisionExtractor
3. Report generation with DEIReportGenerator

This example shows how to analyze policies for DEI compliance issues
using the algorithms and methodologies from the HACC repository.
"""

from complaint_analysis import (
    DEIRiskScorer,
    DEIProvisionExtractor,
    DEIReportGenerator
)


# Sample policy documents for analysis
POLICY_1 = {
    'id': 'Procurement_Policy_2024',
    'text': """
    Section 1. Purpose
    
    This procurement policy establishes diversity, equity, and inclusion
    requirements for all city contracting activities.
    
    Section 2. Contractor Requirements
    
    All contractors shall:
    (a) Implement DEI initiatives targeting historically underrepresented communities
    (b) Demonstrate cultural competence in service delivery
    (c) Provide documentation of minority-owned business enterprise (MBE) and
        women-owned business enterprise (WBE) participation
    (d) Complete implicit bias training for all personnel
    
    Section 3. Enforcement
    
    Failure to comply with these diversity requirements shall result in
    contract termination, monetary penalties, and exclusion from future
    procurement opportunities. This policy is mandatory and enforceable.
    """,
    'source': 'City Procurement Manual 2024',
    'date': '2024-01-15'
}

POLICY_2 = {
    'id': 'Housing_Guidelines',
    'text': """
    The Housing Authority encourages outreach to diverse communities
    and values equity in housing access. Applicants from various backgrounds
    are welcome to apply.
    """,
    'source': 'Housing Authority Guidelines',
    'date': '2023-06-01'
}

POLICY_3 = {
    'id': 'Standard_Contract',
    'text': """
    Contractor shall provide services according to industry standards.
    All work must meet quality specifications and be completed within
    the agreed timeline. Payment terms are net 30 days.
    """,
    'source': 'Standard Service Agreement',
    'date': '2023-12-01'
}


def main():
    """Run complete DEI policy analysis."""
    print('=' * 80)
    print('HACC-INTEGRATED DEI POLICY ANALYSIS')
    print('=' * 80)
    print()
    
    # Initialize analyzers
    risk_scorer = DEIRiskScorer()
    provision_extractor = DEIProvisionExtractor()
    report_generator = DEIReportGenerator(project_name="Sample_DEI_Analysis")
    
    policies = [POLICY_1, POLICY_2, POLICY_3]
    
    print(f'Analyzing {len(policies)} policy documents...')
    print()
    
    # Analyze each policy
    for i, policy in enumerate(policies, 1):
        print(f'{i}. Analyzing: {policy["id"]}')
        print('   ' + '-' * 70)
        
        # Calculate risk
        risk = risk_scorer.calculate_risk(policy['text'])
        print(f'   Risk Score: {risk["score"]}/3 ({risk["level"].upper()})')
        
        # Extract provisions
        provisions = provision_extractor.extract_provisions(
            policy['text'],
            document_type='policy'
        )
        print(f'   Provisions Found: {len(provisions)}')
        
        if provisions:
            binding = sum(1 for p in provisions if p.get('is_binding', False))
            print(f'   Binding Provisions: {binding}')
        
        # Tag applicability
        tags = risk_scorer.tag_applicability(policy['text'])
        if tags:
            print(f'   Applicability: {", ".join(tags)}')
        
        # Show key issues
        if risk['score'] > 0:
            print(f'   Key Issues:')
            for issue in risk['issues'][:2]:
                print(f'     • {issue}')
        
        print()
        
        # Add to report
        metadata = {
            'id': policy['id'],
            'source': policy['source'],
            'date': policy['date'],
            'applicability_tags': tags
        }
        report_generator.add_document_analysis(risk, provisions, metadata)
    
    print('=' * 80)
    print('GENERATING REPORTS')
    print('=' * 80)
    print()
    
    # Generate executive summary
    print('EXECUTIVE SUMMARY')
    print('-' * 80)
    summary = report_generator.generate_executive_summary()
    print(summary)
    print()
    
    # Save reports
    print('=' * 80)
    print('SAVING REPORTS')
    print('=' * 80)
    saved = report_generator.save_reports('/tmp/dei_reports')
    
    for report_type, filepath in saved.items():
        print(f'✓ {report_type}: {filepath}')
    
    print()
    print('=' * 80)
    print('ANALYSIS COMPLETE')
    print('=' * 80)
    print()
    print('Summary:')
    print(f'  - {len(policies)} documents analyzed')
    print(f'  - {len([p for p in policies if risk_scorer.is_problematic(p["text"], threshold=2)])} high/medium risk')
    print(f'  - Reports saved to /tmp/dei_reports/')
    print()
    print('Review the executive summary for prioritized findings and action items.')
    

if __name__ == '__main__':
    main()
