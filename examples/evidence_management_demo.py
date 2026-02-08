#!/usr/bin/env python3
"""
Example: Evidence Management System

Demonstrates how to submit, store, and analyze evidence using
IPFS for storage and DuckDB for state management.
"""

import tempfile
import os
from pathlib import Path


def create_sample_evidence_files():
    """Create sample evidence files for demonstration."""
    temp_dir = Path(tempfile.mkdtemp())
    
    files = {
        'contract.txt': b'EMPLOYMENT CONTRACT\n\nThis agreement is made between...',
        'email.txt': b'From: defendant@example.com\nSubject: Re: Contract Terms\n\nI confirm that...',
        'invoice.txt': b'INVOICE #12345\nDate: 2023-01-15\nAmount: $50,000\n...'
    }
    
    file_paths = {}
    for filename, content in files.items():
        file_path = temp_dir / filename
        file_path.write_bytes(content)
        file_paths[filename] = str(file_path)
    
    return temp_dir, file_paths


def main():
    """Run the evidence management demonstration."""
    print("=" * 70)
    print("Evidence Management System - Demonstration")
    print("=" * 70)
    print()
    
    print("This example demonstrates the evidence management system that:")
    print("1. Stores evidence in IPFS (returns Content IDs)")
    print("2. Tracks evidence state in DuckDB")
    print("3. Analyzes evidence for legal claims")
    print()
    
    # Create sample evidence files
    print("SETUP: Creating sample evidence files")
    print("-" * 70)
    temp_dir, file_paths = create_sample_evidence_files()
    print(f"✓ Created {len(file_paths)} sample evidence files in {temp_dir}")
    for filename in file_paths:
        print(f"  - {filename}")
    print()
    
    # Simulate evidence submission
    print("STEP 1: Submitting Evidence to IPFS")
    print("-" * 70)
    
    evidence_records = []
    for filename, file_path in file_paths.items():
        # Simulate what would happen
        with open(file_path, 'rb') as f:
            data = f.read()
        size = len(data)
        
        # Simulated CID (in real system, this would come from IPFS)
        import hashlib
        cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
        
        evidence_records.append({
            'filename': filename,
            'cid': cid,
            'size': size,
            'type': 'document' if filename.endswith('.txt') else 'email'
        })
        
        print(f"✓ {filename}")
        print(f"  CID: {cid}")
        print(f"  Size: {size} bytes")
        print()
    
    # Simulate DuckDB storage
    print("STEP 2: Recording Evidence Metadata in DuckDB")
    print("-" * 70)
    
    evidence_db = []
    for i, record in enumerate(evidence_records, 1):
        evidence_entry = {
            'id': i,
            'user_id': 'demo_user',
            'cid': record['cid'],
            'type': record['type'],
            'size': record['size'],
            'claim_type': 'breach of contract',
            'description': f"Evidence: {record['filename']}"
        }
        evidence_db.append(evidence_entry)
        
        print(f"✓ Record #{i} created")
        print(f"  CID: {record['cid'][:20]}...")
        print(f"  Type: {record['type']}")
        print(f"  Claim: {evidence_entry['claim_type']}")
    print()
    
    # Simulate retrieval
    print("STEP 3: Retrieving Evidence by User")
    print("-" * 70)
    
    user_evidence = [e for e in evidence_db if e['user_id'] == 'demo_user']
    print(f"Found {len(user_evidence)} evidence items for user 'demo_user':")
    print()
    
    for evidence in user_evidence:
        print(f"Record #{evidence['id']}:")
        print(f"  Type: {evidence['type']}")
        print(f"  CID: {evidence['cid'][:30]}...")
        print(f"  Size: {evidence['size']} bytes")
        print(f"  Claim: {evidence['claim_type']}")
        print()
    
    # Simulate analysis
    print("STEP 4: Analyzing Evidence for Claim")
    print("-" * 70)
    
    claim_type = 'breach of contract'
    claim_evidence = [e for e in evidence_db if e['claim_type'] == claim_type]
    
    evidence_by_type = {}
    for e in claim_evidence:
        ev_type = e['type']
        evidence_by_type[ev_type] = evidence_by_type.get(ev_type, 0) + 1
    
    print(f"Analysis for claim: {claim_type}")
    print(f"Total evidence items: {len(claim_evidence)}")
    print(f"Evidence breakdown:")
    for ev_type, count in evidence_by_type.items():
        print(f"  - {ev_type}: {count} items")
    print()
    
    # Recommendations
    print("STEP 5: AI-Powered Evidence Recommendations")
    print("-" * 70)
    print("Based on submitted evidence:")
    print()
    print("✓ Strengths:")
    print("  - Contract document provided (establishes agreement)")
    print("  - Email correspondence (shows communication)")
    print("  - Invoice (demonstrates financial terms)")
    print()
    print("⚠ Gaps:")
    print("  - Consider adding proof of performance")
    print("  - Include evidence of damages")
    print("  - Gather breach notification communications")
    print()
    print("→ Next Steps:")
    print("  1. Submit evidence of your performance under contract")
    print("  2. Document the specific breach incidents")
    print("  3. Compile evidence of financial damages")
    print()
    
    # Statistics
    print("STEP 6: Evidence Statistics")
    print("-" * 70)
    
    total_size = sum(e['size'] for e in evidence_db)
    total_count = len(evidence_db)
    type_count = len(evidence_by_type)
    
    print(f"Database Statistics:")
    print(f"  Total items: {total_count}")
    print(f"  Total storage: {total_size} bytes ({total_size/1024:.2f} KB)")
    print(f"  Evidence types: {type_count}")
    print(f"  Users: 1")
    print()
    
    # Cleanup
    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("The evidence management system provides:")
    print("  ✓ Immutable storage in IPFS (content-addressable)")
    print("  ✓ Fast state management with DuckDB")
    print("  ✓ Evidence tracking by CID")
    print("  ✓ User and claim association")
    print("  ✓ AI-powered evidence analysis")
    print()
    print("In production:")
    print("  - Evidence is actually stored in IPFS")
    print("  - Metadata persists in DuckDB database")
    print("  - LLM provides detailed analysis and recommendations")
    print("  - Evidence can be retrieved anytime by CID")
    print()
    
    # Cleanup temp files
    import shutil
    shutil.rmtree(temp_dir)
    print(f"✓ Cleaned up temporary files")
    print()
    print("=" * 70)


if __name__ == '__main__':
    main()
