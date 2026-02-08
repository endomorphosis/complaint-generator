#!/usr/bin/env python3
"""
HACC Integration Example - Complaint Evidence Pipeline

This example demonstrates how to integrate HACC scripts with the
complaint-generator mediator for automated evidence gathering.

Requirements:
    pip install requests beautifulsoup4
    export BRAVE_API_KEY="your_key_here"
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComplaintEvidenceGatherer:
    """
    Integration wrapper for HACC scripts adapted for complaint evidence gathering.
    
    This class demonstrates how to use HACC scripts for:
    1. Searching for complaint-relevant evidence
    2. Downloading and deduplicating documents
    3. Parsing PDF evidence
    4. Indexing with complaint-specific keywords
    5. Generating evidence reports
    """
    
    def __init__(self, base_dir: str = "evidence_workspace"):
        """Initialize evidence gatherer with workspace directory."""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up directory structure
        self.raw_dir = self.base_dir / "documents" / "raw"
        self.parsed_dir = self.base_dir / "documents" / "parsed"
        self.search_dir = self.base_dir / "search_results"
        self.report_dir = self.base_dir / "reports"
        
        for dir_path in [self.raw_dir, self.parsed_dir, self.search_dir, self.report_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized evidence workspace at {self.base_dir}")
    
    def search_evidence(self, complaint_type: str, keywords: List[str]) -> List[Dict]:
        """
        Search for evidence using Brave Search API.
        
        Args:
            complaint_type: Type of complaint (e.g., 'housing', 'employment')
            keywords: List of search keywords
            
        Returns:
            List of search results with URLs and metadata
        """
        logger.info(f"Searching for {complaint_type} evidence with keywords: {keywords}")
        
        # Simulate HACC collect_brave.py integration
        # In real implementation, import and use BraveCollector
        queries = self._build_search_queries(complaint_type, keywords)
        
        logger.info(f"Generated {len(queries)} search queries")
        for query in queries:
            logger.info(f"  - {query}")
        
        # Placeholder for actual Brave API calls
        # collector = BraveCollector()
        # results = collector.batch_search(queries)
        # collector.save_results()
        
        return queries  # Return queries for demonstration
    
    def _build_search_queries(self, complaint_type: str, keywords: List[str]) -> List[str]:
        """Build targeted search queries based on complaint type."""
        
        # Domain targets for different complaint types
        domain_map = {
            'housing': ['hud.gov', 'oregon.gov', 'clackamas.us'],
            'employment': ['eeoc.gov', 'oregon.gov', 'dol.gov'],
            'civil_rights': ['justice.gov', 'oregon.gov', 'aclu.org']
        }
        
        domains = domain_map.get(complaint_type, ['gov'])
        queries = []
        
        for domain in domains:
            for keyword in keywords:
                # Search for PDFs (likely policies, forms, regulations)
                queries.append(f'site:{domain} "{keyword}" filetype:pdf')
                
                # Search for HTML content (procedures, guidance)
                queries.append(f'site:{domain} "{keyword}" ("policy" OR "procedure")')
        
        return queries
    
    def download_evidence(self, urls: List[str]) -> List[str]:
        """
        Download evidence documents with deduplication.
        
        Args:
            urls: List of URLs to download
            
        Returns:
            List of local file paths
        """
        logger.info(f"Downloading {len(urls)} evidence documents...")
        
        # Simulate HACC download_manager.py integration
        # In real implementation, use DownloadManager to download PDFs
        
        logger.info(f"Downloaded to {self.raw_dir}")
        return []
    
    def parse_documents(self) -> List[str]:
        """
        Parse all downloaded PDFs with OCR fallback.
        
        Returns:
            List of parsed text file paths
        """
        logger.info("Parsing PDF documents...")
        
        # Simulate HACC parse_pdfs.py integration
        # In real implementation, use PDFParser to batch parse documents
        
        logger.info(f"Parsed documents saved to {self.parsed_dir}")
        return []
    
    def index_evidence(self, complaint_keywords: List[str]) -> Dict:
        """
        Index parsed documents with complaint-specific keywords.
        
        Args:
            complaint_keywords: Keywords relevant to this complaint
            
        Returns:
            Index data structure
        """
        logger.info("Indexing evidence documents...")
        
        # Simulate HACC index_and_tag.py integration
        # In real implementation, use DocumentIndexer with complaint-specific keywords
        
        logger.info(f"Index saved to {self.base_dir / 'index.json'}")
        return {}
    
    def generate_report(self, complaint_id: str) -> str:
        """
        Generate evidence summary report.
        
        Args:
            complaint_id: Complaint identifier
            
        Returns:
            Report text
        """
        logger.info(f"Generating report for complaint {complaint_id}...")
        
        # Simulate HACC report_generator.py integration
        # In real implementation:
        # generator = ReportGenerator(output_dir=str(self.report_dir))
        # generator.load_index(str(self.base_dir / "index.json"))
        # summary = generator.generate_one_page_summary()
        
        report_path = self.report_dir / f"complaint_{complaint_id}_evidence_report.txt"
        logger.info(f"Report saved to {report_path}")
        return str(report_path)
    
    def run_full_pipeline(self, complaint_data: Dict) -> Dict:
        """
        Execute full evidence gathering pipeline.
        
        Args:
            complaint_data: Dictionary with complaint information
                {
                    'id': 'COMPLAINT-001',
                    'type': 'housing',
                    'keywords': ['fair housing', 'disability', 'reasonable accommodation'],
                    'description': 'Landlord refused reasonable accommodation request...'
                }
        
        Returns:
            Pipeline results with evidence paths and report
        """
        logger.info("="*80)
        logger.info(f"Starting evidence gathering pipeline for complaint {complaint_data['id']}")
        logger.info("="*80)
        
        # Step 1: Search for evidence
        logger.info("\n[Step 1/5] Searching for evidence...")
        queries = self.search_evidence(
            complaint_type=complaint_data['type'],
            keywords=complaint_data['keywords']
        )
        
        # Step 2: Download evidence (simulated)
        logger.info("\n[Step 2/5] Downloading evidence documents...")
        sample_urls = [
            "https://hud.gov/fair_housing_act.pdf",
            "https://oregon.gov/housing_authority_procedures.pdf"
        ]
        downloaded_files = self.download_evidence(sample_urls)
        
        # Step 3: Parse documents
        logger.info("\n[Step 3/5] Parsing PDF documents...")
        parsed_files = self.parse_documents()
        
        # Step 4: Index with keywords
        logger.info("\n[Step 4/5] Indexing evidence...")
        self.index_evidence(complaint_data['keywords'])
        
        # Step 5: Generate report
        logger.info("\n[Step 5/5] Generating evidence report...")
        report_path = self.generate_report(complaint_data['id'])
        
        logger.info("\n" + "="*80)
        logger.info("Evidence gathering pipeline completed successfully!")
        logger.info("="*80)
        
        return {
            'complaint_id': complaint_data['id'],
            'queries_generated': len(queries),
            'documents_downloaded': len(downloaded_files),
            'documents_parsed': len(parsed_files),
            'index_path': str(self.base_dir / "index.json"),
            'report_path': report_path
        }


def main():
    """Example usage of the ComplaintEvidenceGatherer."""
    
    # Example complaint data
    complaint = {
        'id': 'COMPLAINT-001',
        'type': 'housing',
        'keywords': [
            'fair housing',
            'disability discrimination',
            'reasonable accommodation',
            'service animal'
        ],
        'description': 'Landlord refused to allow service animal despite medical documentation.'
    }
    
    # Initialize gatherer
    gatherer = ComplaintEvidenceGatherer(base_dir="evidence_workspace")
    
    # Run full pipeline
    results = gatherer.run_full_pipeline(complaint)
    
    # Display results
    print("\n" + "="*80)
    print("PIPELINE RESULTS")
    print("="*80)
    for key, value in results.items():
        print(f"{key:25s}: {value}")
    print("="*80)
    
    return results


if __name__ == "__main__":
    try:
        results = main()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
