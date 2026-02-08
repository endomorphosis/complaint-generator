#!/usr/bin/env python3
"""
Example: Web Evidence Discovery System

Demonstrates automatic evidence discovery using Brave Search,
Common Crawl archives, and other web archiving tools.
"""


def main():
    """Run the web evidence discovery demonstration."""
    print("=" * 70)
    print("Web Evidence Discovery System - Demonstration")
    print("=" * 70)
    print()
    
    print("This system demonstrates automatic evidence discovery using:")
    print("1. Brave Search API - Search current web content")
    print("2. Common Crawl Search Engine - Search archived web pages")
    print("3. Web archiving tools - Additional evidence sources")
    print()
    
    # Scenario
    print("SCENARIO: Employment Discrimination Case")
    print("-" * 70)
    complaint = """
    The plaintiff was employed as a software engineer and reported
    discrimination to HR. Shortly after, they were terminated.
    
    Claims:
    - Employment discrimination
    - Retaliation for reporting
    - Wrongful termination
    """
    print(complaint)
    print()
    
    # Step 1: Generate Keywords
    print("STEP 1: Generating Search Keywords for Each Claim")
    print("-" * 70)
    
    claim_keywords = {
        'employment discrimination': [
            'employment discrimination evidence',
            'Title VII discrimination',
            'workplace discrimination documentation',
            'EEOC discrimination complaint'
        ],
        'retaliation': [
            'whistleblower retaliation',
            'retaliation for reporting',
            'adverse employment action',
            'protected activity retaliation'
        ],
        'wrongful termination': [
            'wrongful termination evidence',
            'unlawful dismissal',
            'termination in violation of policy',
            'employment contract breach'
        ]
    }
    
    for claim, keywords in claim_keywords.items():
        print(f"\n{claim.upper()}:")
        for kw in keywords:
            print(f"  - {kw}")
    print()
    
    # Step 2: Web Search
    print("STEP 2: Searching Web Sources")
    print("-" * 70)
    
    web_results = {
        'brave_search': [
            {
                'title': 'EEOC Charge Statistics - Employment Discrimination',
                'url': 'https://www.eeoc.gov/statistics/charge-statistics',
                'description': 'Annual statistics on employment discrimination charges...',
                'source_type': 'brave_search',
                'relevance': 0.85
            },
            {
                'title': 'Understanding Retaliation Claims Under Title VII',
                'url': 'https://www.eeoc.gov/retaliation',
                'description': 'Information about retaliation claims and protections...',
                'source_type': 'brave_search',
                'relevance': 0.90
            },
            {
                'title': 'Wrongful Termination: What You Need to Know',
                'url': 'https://www.dol.gov/wrongful-termination',
                'description': 'Guide to understanding wrongful termination laws...',
                'source_type': 'brave_search',
                'relevance': 0.75
            }
        ],
        'common_crawl': [
            {
                'title': 'Company XYZ - Employee Handbook (Archived)',
                'url': 'https://archive.org/details/company-handbook-2020',
                'description': 'Archived company policies on discrimination and termination...',
                'source_type': 'common_crawl',
                'relevance': 0.80
            },
            {
                'title': 'Employment Law Blog - Retaliation Cases',
                'url': 'https://employmentlaw.example.com/retaliation-2023',
                'description': 'Analysis of recent retaliation case outcomes...',
                'source_type': 'common_crawl',
                'relevance': 0.70
            }
        ]
    }
    
    print("BRAVE SEARCH RESULTS:")
    for result in web_results['brave_search']:
        print(f"  ✓ {result['title']}")
        print(f"    URL: {result['url']}")
        print(f"    Relevance: {result['relevance']:.0%}")
    
    print("\nCOMMON CRAWL ARCHIVE RESULTS:")
    for result in web_results['common_crawl']:
        print(f"  ✓ {result['title']}")
        print(f"    URL: {result['url']}")
        print(f"    Relevance: {result['relevance']:.0%}")
    
    total_found = len(web_results['brave_search']) + len(web_results['common_crawl'])
    print(f"\nTotal: {total_found} potential evidence items discovered")
    print()
    
    # Step 3: Validation
    print("STEP 3: Validating Discovered Evidence")
    print("-" * 70)
    
    min_relevance = 0.6
    print(f"Minimum relevance threshold: {min_relevance:.0%}")
    print()
    
    validated = []
    skipped = []
    
    all_results = web_results['brave_search'] + web_results['common_crawl']
    for result in all_results:
        if result['relevance'] >= min_relevance:
            validated.append(result)
            print(f"✓ VALIDATED: {result['title']}")
            print(f"  Relevance: {result['relevance']:.0%}")
            print(f"  Source: {result['source_type']}")
        else:
            skipped.append(result)
            print(f"✗ SKIPPED: {result['title']}")
            print(f"  Relevance: {result['relevance']:.0%} (below threshold)")
    
    print(f"\nValidated: {len(validated)} items")
    print(f"Skipped: {len(skipped)} items")
    print()
    
    # Step 4: Storage
    print("STEP 4: Storing Evidence in IPFS + DuckDB")
    print("-" * 70)
    
    import hashlib
    
    stored_evidence = []
    for result in validated:
        # Simulate IPFS storage
        evidence_json = str(result).encode('utf-8')
        cid = f"Qm{hashlib.sha256(evidence_json).hexdigest()[:44]}"
        
        stored = {
            'cid': cid,
            'title': result['title'],
            'url': result['url'],
            'source_type': result['source_type'],
            'relevance': result['relevance'],
            'auto_discovered': True
        }
        stored_evidence.append(stored)
        
        print(f"✓ Stored: {result['title']}")
        print(f"  CID: {cid}")
        print(f"  Source: {result['source_type']}")
    
    print(f"\nTotal stored: {len(stored_evidence)} evidence items")
    print()
    
    # Step 5: Results Summary
    print("STEP 5: Evidence Discovery Summary")
    print("-" * 70)
    
    by_source = {}
    by_claim = {}
    
    for evidence in stored_evidence:
        source = evidence['source_type']
        by_source[source] = by_source.get(source, 0) + 1
    
    # Simulate claim assignment
    by_claim = {
        'employment discrimination': 2,
        'retaliation': 3,
        'wrongful termination': 2
    }
    
    print("Evidence by Source:")
    for source, count in by_source.items():
        print(f"  {source}: {count} items")
    
    print("\nEvidence by Claim Type:")
    for claim, count in by_claim.items():
        print(f"  {claim}: {count} items")
    
    print(f"\nTotal auto-discovered evidence: {len(stored_evidence)}")
    avg_relevance = sum(e['relevance'] for e in stored_evidence) / len(stored_evidence)
    print(f"Average relevance: {avg_relevance:.0%}")
    print()
    
    # Step 6: Integration
    print("STEP 6: Integration with User Evidence")
    print("-" * 70)
    
    user_evidence_count = 3  # Simulated
    auto_evidence_count = len(stored_evidence)
    total_evidence = user_evidence_count + auto_evidence_count
    
    print(f"User-submitted evidence: {user_evidence_count}")
    print(f"Auto-discovered evidence: {auto_evidence_count}")
    print(f"Total evidence in case: {total_evidence}")
    print()
    
    print("Evidence Database includes:")
    print("  • Employment contracts (user-submitted)")
    print("  • Email correspondence (user-submitted)")
    print("  • Termination letter (user-submitted)")
    print("  • EEOC statistics (auto-discovered)")
    print("  • Legal guidance on retaliation (auto-discovered)")
    print("  • Company handbook (auto-discovered)")
    print("  • Case law analysis (auto-discovered)")
    print("  • DOL wrongful termination guide (auto-discovered)")
    print()
    
    # Summary
    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("The web evidence discovery system provides:")
    print("  ✓ Automatic evidence search from multiple web sources")
    print("  ✓ Current content via Brave Search")
    print("  ✓ Historical content via Common Crawl archives")
    print("  ✓ AI-powered relevance validation")
    print("  ✓ IPFS storage with content-addressable IDs")
    print("  ✓ DuckDB tracking with metadata")
    print("  ✓ Seamless integration with user evidence")
    print()
    print("In production:")
    print("  - Brave Search API provides real-time web results")
    print("  - Common Crawl indexes billions of archived pages")
    print("  - LLM validates relevance and quality")
    print("  - Evidence stores in IPFS for integrity")
    print("  - Metadata persists in DuckDB for fast queries")
    print("  - Works alongside manually submitted evidence")
    print()
    print("=" * 70)


if __name__ == '__main__':
    main()
