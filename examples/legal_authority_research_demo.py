#!/usr/bin/env python3
"""
Example: Legal Authority Research System

Demonstrates automated legal research using web archiving and legal scrapers
to find and store relevant authorities in DuckDB.
"""

from unittest.mock import Mock


def main():
    """Run the legal authority research demonstration."""
    print("=" * 70)
    print("Legal Authority Research System - Demonstration")
    print("=" * 70)
    print()
    
    print("This system demonstrates automatic legal research that:")
    print("1. Searches multiple legal sources (US Code, Federal Register, etc.)")
    print("2. Uses web archiving tools to find relevant laws")
    print("3. Stores authorities in DuckDB for analysis")
    print("4. Provides AI-powered recommendations")
    print()
    
    # Simulate case scenario
    print("SCENARIO: Employment Discrimination Case")
    print("-" * 70)
    complaint = """
    The plaintiff was employed as a software engineer and was terminated
    after reporting discriminatory practices. The plaintiff alleges:
    - Unlawful termination in retaliation for whistleblowing
    - Discrimination based on protected characteristics
    - Violation of employment contract terms
    """
    print(complaint)
    print()
    
    # Step 1: Classify Claims
    print("STEP 1: Analyzing Complaint & Classifying Claims")
    print("-" * 70)
    
    claim_types = [
        'employment discrimination',
        'wrongful termination',
        'breach of contract'
    ]
    
    print("Identified claim types:")
    for claim in claim_types:
        print(f"  ✓ {claim}")
    print()
    
    # Step 2: Search Legal Authorities
    print("STEP 2: Searching Legal Authorities")
    print("-" * 70)
    
    authorities_found = {
        'employment discrimination': {
            'statutes': [
                {
                    'citation': '42 U.S.C. § 2000e',
                    'title': 'Title VII of the Civil Rights Act',
                    'source': 'us_code'
                },
                {
                    'citation': '42 U.S.C. § 1981',
                    'title': 'Equal Rights Under the Law',
                    'source': 'us_code'
                }
            ],
            'regulations': [
                {
                    'citation': '29 C.F.R. § 1604',
                    'title': 'EEOC Guidelines on Discrimination',
                    'source': 'federal_register'
                }
            ],
            'case_law': [
                {
                    'citation': 'McDonnell Douglas Corp. v. Green, 411 U.S. 792',
                    'title': 'Burden-Shifting Framework',
                    'source': 'recap'
                }
            ]
        },
        'wrongful termination': {
            'statutes': [
                {
                    'citation': '29 U.S.C. § 2615',
                    'title': 'Prohibition of Interference with Rights',
                    'source': 'us_code'
                }
            ],
            'case_law': [
                {
                    'citation': 'Foley v. Interactive Data Corp., 47 Cal. 3d 654',
                    'title': 'Wrongful Termination in Violation of Public Policy',
                    'source': 'recap'
                }
            ]
        },
        'breach of contract': {
            'statutes': [
                {
                    'citation': 'UCC § 2-301',
                    'title': 'General Obligations of Parties',
                    'source': 'us_code'
                }
            ]
        }
    }
    
    total_authorities = 0
    for claim_type, sources in authorities_found.items():
        claim_total = sum(len(v) for v in sources.values())
        total_authorities += claim_total
        print(f"✓ {claim_type}: {claim_total} authorities found")
        for source_type, auths in sources.items():
            if auths:
                print(f"  - {source_type}: {len(auths)}")
    
    print(f"\nTotal: {total_authorities} legal authorities discovered")
    print()
    
    # Step 3: Store in DuckDB
    print("STEP 3: Storing Authorities in DuckDB")
    print("-" * 70)
    
    print("Creating legal_authorities table with schema:")
    print("  - id, user_id, complaint_id, claim_type")
    print("  - authority_type, source, citation, title")
    print("  - content, url, metadata, relevance_score")
    print("  - timestamp, search_query")
    print()
    
    stored_count = 0
    for claim_type, sources in authorities_found.items():
        for source_type, auths in sources.items():
            for auth in auths:
                stored_count += 1
                print(f"✓ Stored: {auth['citation']}")
    
    print(f"\nTotal: {stored_count} authorities stored in DuckDB")
    print()
    
    # Step 4: Retrieve and Display
    print("STEP 4: Retrieving Stored Authorities by Claim")
    print("-" * 70)
    
    for claim_type in claim_types:
        authorities = authorities_found.get(claim_type, {})
        total = sum(len(v) for v in authorities.values())
        
        print(f"\n{claim_type.upper()}:")
        print(f"  Total authorities: {total}")
        
        # Show top authorities
        if 'statutes' in authorities and authorities['statutes']:
            print(f"  Key statutes:")
            for auth in authorities['statutes'][:2]:
                print(f"    - {auth['citation']}: {auth['title']}")
        
        if 'case_law' in authorities and authorities['case_law']:
            print(f"  Key cases:")
            for auth in authorities['case_law'][:1]:
                print(f"    - {auth['citation']}: {auth['title']}")
    print()
    
    # Step 5: AI Analysis
    print("STEP 5: AI-Powered Analysis & Recommendations")
    print("-" * 70)
    
    print("\nEMPLOYMENT DISCRIMINATION:")
    print("  Strength: STRONG legal foundation")
    print("  Key Authorities:")
    print("    - Title VII (42 U.S.C. § 2000e) - Primary federal statute")
    print("    - McDonnell Douglas framework - Establishes burden-shifting")
    print("  Recommendation: Focus on prima facie case elements")
    print()
    
    print("WRONGFUL TERMINATION:")
    print("  Strength: MODERATE legal foundation")
    print("  Key Authorities:")
    print("    - 29 U.S.C. § 2615 - Protects against interference")
    print("    - Foley v. Interactive Data - Public policy exception")
    print("  Recommendation: Gather evidence of public policy violation")
    print()
    
    print("BREACH OF CONTRACT:")
    print("  Strength: SUFFICIENT legal foundation")
    print("  Key Authorities:")
    print("    - UCC § 2-301 - General obligations framework")
    print("  Recommendation: Obtain employment contract and document breach")
    print()
    
    # Step 6: Statistics
    print("STEP 6: Research Statistics")
    print("-" * 70)
    
    print(f"Database Statistics:")
    print(f"  Total authorities: {stored_count}")
    print(f"  Claim types covered: {len(claim_types)}")
    print(f"  Authority types: statutes, regulations, case law")
    print(f"  Sources: US Code, Federal Register, RECAP Archive")
    print()
    
    # Summary
    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("The legal authority research system provides:")
    print("  ✓ Multi-source legal research (US Code, Federal Register, Cases)")
    print("  ✓ Web archiving integration for finding relevant laws")
    print("  ✓ DuckDB storage with fast SQL queries")
    print("  ✓ Citation tracking and relevance scoring")
    print("  ✓ AI-powered analysis and recommendations")
    print("  ✓ Automatic research based on complaint classification")
    print()
    print("In production:")
    print("  - Authorities are actually fetched from legal databases")
    print("  - Web archiving searches Common Crawl for legal content")
    print("  - Metadata persists in DuckDB for fast retrieval")
    print("  - LLM analyzes authorities and provides detailed guidance")
    print("  - Integrates with evidence management and legal analysis")
    print()
    print("=" * 70)


if __name__ == '__main__':
    main()
