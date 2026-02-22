"""
Unit tests for Batch 218: HybridDocumentIndexer analysis methods.

Tests the 10 document indexing tracking and statistics methods added to HybridDocumentIndexer.
"""

import pytest
from complaint_analysis.indexer import HybridDocumentIndexer


@pytest.fixture
def indexer():
    """Create a HybridDocumentIndexer instance for testing (without embeddings)."""
    return HybridDocumentIndexer(enable_embeddings=False)


def create_mock_indexed_doc(risk_level='minimal', relevance_score=0.5,
                            applicability=None, provision_count=0,
                            embedding_available=False):
    """Helper to create a mock indexed document result."""
    if applicability is None:
        applicability = []
    
    return {
        'text_length': 100,
        'metadata': {},
        'indexed_date': '2024-01-01T00:00:00',
        'embedding_available': embedding_available,
        'keywords': {
            'complaint': [],
            'evidence': [],
            'legal': [],
            'binding': []
        },
        'applicability': applicability,
        'legal_provisions': {
            'provision_count': provision_count,
            'provisions': []
        },
        'risk_score': {'minimal': 0, 'low': 1, 'medium': 2, 'high': 3}[risk_level],
        'risk_level': risk_level,
        'risk_factors': [],
        'relevance_score': relevance_score
    }


# ============================================================================ #
# Test total_indexed_documents()
# ============================================================================ #

class TestTotalIndexedDocuments:
    def test_no_documents(self, indexer):
        assert indexer.total_indexed_documents() == 0
    
    def test_after_manual_add(self, indexer):
        indexer._indexed_documents.append(create_mock_indexed_doc())
        assert indexer.total_indexed_documents() == 1
    
    def test_multiple_documents(self, indexer):
        for i in range(5):
            indexer._indexed_documents.append(create_mock_indexed_doc())
        assert indexer.total_indexed_documents() == 5


# ============================================================================ #
# Test documents_by_risk_level()
# ============================================================================ #

class TestDocumentsByRiskLevel:
    def test_no_documents(self, indexer):
        assert indexer.documents_by_risk_level('high') == 0
    
    def test_no_matching_level(self, indexer):
        indexer._indexed_documents.append(create_mock_indexed_doc(risk_level='low'))
        assert indexer.documents_by_risk_level('high') == 0
    
    def test_single_matching_level(self, indexer):
        indexer._indexed_documents.append(create_mock_indexed_doc(risk_level='high'))
        assert indexer.documents_by_risk_level('high') == 1
    
    def test_multiple_levels(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(risk_level='high'),
            create_mock_indexed_doc(risk_level='low'),
            create_mock_indexed_doc(risk_level='high'),
            create_mock_indexed_doc(risk_level='medium'),
        ])
        assert indexer.documents_by_risk_level('high') == 2
        assert indexer.documents_by_risk_level('low') == 1
        assert indexer.documents_by_risk_level('medium') == 1


# ============================================================================ #
# Test risk_level_distribution()
# ============================================================================ #

class TestRiskLevelDistribution:
    def test_no_documents(self, indexer):
        assert indexer.risk_level_distribution() == {}
    
    def test_single_level(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(risk_level='medium'),
            create_mock_indexed_doc(risk_level='medium'),
        ])
        assert indexer.risk_level_distribution() == {'medium': 2}
    
    def test_multiple_levels(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(risk_level='minimal'),
            create_mock_indexed_doc(risk_level='high'),
            create_mock_indexed_doc(risk_level='low'),
            create_mock_indexed_doc(risk_level='high'),
        ])
        dist = indexer.risk_level_distribution()
        assert dist == {'minimal': 1, 'high': 2, 'low': 1}


# ============================================================================ #
# Test average_relevance_score()
# ============================================================================ #

class TestAverageRelevanceScore:
    def test_no_documents(self, indexer):
        assert indexer.average_relevance_score() == 0.0
    
    def test_single_document(self, indexer):
        indexer._indexed_documents.append(create_mock_indexed_doc(relevance_score=0.8))
        assert abs(indexer.average_relevance_score() - 0.8) < 0.01
    
    def test_multiple_documents(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(relevance_score=0.2),
            create_mock_indexed_doc(relevance_score=0.4),
            create_mock_indexed_doc(relevance_score=0.6),
        ])
        # Average: (0.2 + 0.4 + 0.6) / 3 = 0.4
        assert abs(indexer.average_relevance_score() - 0.4) < 0.01


# ============================================================================ #
# Test maximum_relevance_score()
# ============================================================================ #

class TestMaximumRelevanceScore:
    def test_no_documents(self, indexer):
        assert indexer.maximum_relevance_score() == 0.0
    
    def test_single_document(self, indexer):
        indexer._indexed_documents.append(create_mock_indexed_doc(relevance_score=0.7))
        assert abs(indexer.maximum_relevance_score() - 0.7) < 0.01
    
    def test_multiple_documents(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(relevance_score=0.3),
            create_mock_indexed_doc(relevance_score=0.9),
            create_mock_indexed_doc(relevance_score=0.5),
        ])
        assert abs(indexer.maximum_relevance_score() - 0.9) < 0.01


# ============================================================================ #
# Test documents_by_applicability()
# ============================================================================ #

class TestDocumentsByApplicability:
    def test_no_documents(self, indexer):
        assert indexer.documents_by_applicability('housing') == 0
    
    def test_no_matching_tag(self, indexer):
        indexer._indexed_documents.append(
            create_mock_indexed_doc(applicability=['employment'])
        )
        assert indexer.documents_by_applicability('housing') == 0
    
    def test_single_matching_tag(self, indexer):
        indexer._indexed_documents.append(
            create_mock_indexed_doc(applicability=['housing'])
        )
        assert indexer.documents_by_applicability('housing') == 1
    
    def test_multiple_tags(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(applicability=['housing']),
            create_mock_indexed_doc(applicability=['employment', 'housing']),
            create_mock_indexed_doc(applicability=['consumer']),
        ])
        assert indexer.documents_by_applicability('housing') == 2
        assert indexer.documents_by_applicability('employment') == 1
        assert indexer.documents_by_applicability('consumer') == 1


# ============================================================================ #
# Test applicability_distribution()
# ============================================================================ #

class TestApplicabilityDistribution:
    def test_no_documents(self, indexer):
        assert indexer.applicability_distribution() == {}
    
    def test_single_tag(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(applicability=['housing']),
            create_mock_indexed_doc(applicability=['housing']),
        ])
        assert indexer.applicability_distribution() == {'housing': 2}
    
    def test_multiple_tags(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(applicability=['housing']),
            create_mock_indexed_doc(applicability=['employment', 'housing']),
            create_mock_indexed_doc(applicability=['consumer']),
        ])
        dist = indexer.applicability_distribution()
        # housing appears 2 times, employment 1, consumer 1
        assert dist == {'housing': 2, 'employment': 1, 'consumer': 1}


# ============================================================================ #
# Test average_legal_provisions()
# ============================================================================ #

class TestAverageLegalProvisions:
    def test_no_documents(self, indexer):
        assert indexer.average_legal_provisions() == 0.0
    
    def test_single_document(self, indexer):
        indexer._indexed_documents.append(create_mock_indexed_doc(provision_count=5))
        assert abs(indexer.average_legal_provisions() - 5.0) < 0.01
    
    def test_multiple_documents(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(provision_count=2),
            create_mock_indexed_doc(provision_count=4),
            create_mock_indexed_doc(provision_count=6),
        ])
        # Average: (2 + 4 + 6) / 3 = 4.0
        assert abs(indexer.average_legal_provisions() - 4.0) < 0.01


# ============================================================================ #
# Test high_risk_documents_percentage()
# ============================================================================ #

class TestHighRiskDocumentsPercentage:
    def test_no_documents(self, indexer):
        assert indexer.high_risk_documents_percentage() == 0.0
    
    def test_no_high_risk(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(risk_level='minimal'),
            create_mock_indexed_doc(risk_level='low'),
        ])
        assert indexer.high_risk_documents_percentage() == 0.0
    
    def test_all_high_risk(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(risk_level='high'),
            create_mock_indexed_doc(risk_level='high'),
        ])
        assert indexer.high_risk_documents_percentage() == 100.0
    
    def test_mixed_risk(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(risk_level='high'),
            create_mock_indexed_doc(risk_level='low'),
            create_mock_indexed_doc(risk_level='high'),
            create_mock_indexed_doc(risk_level='medium'),
        ])
        # 2 high out of 4 = 50%
        assert abs(indexer.high_risk_documents_percentage() - 50.0) < 0.01


# ============================================================================ #
# Test documents_with_embeddings()
# ============================================================================ #

class TestDocumentsWithEmbeddings:
    def test_no_documents(self, indexer):
        assert indexer.documents_with_embeddings() == 0
    
    def test_no_embeddings(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(embedding_available=False),
            create_mock_indexed_doc(embedding_available=False),
        ])
        assert indexer.documents_with_embeddings() == 0
    
    def test_all_with_embeddings(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(embedding_available=True),
            create_mock_indexed_doc(embedding_available=True),
        ])
        assert indexer.documents_with_embeddings() == 2
    
    def test_mixed_embeddings(self, indexer):
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(embedding_available=True),
            create_mock_indexed_doc(embedding_available=False),
            create_mock_indexed_doc(embedding_available=True),
        ])
        assert indexer.documents_with_embeddings() == 2


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch218Integration:
    def test_comprehensive_indexer_analysis(self, indexer):
        """Test that all Batch 218 methods work together correctly."""
        # Populate with various indexed documents
        indexer._indexed_documents.extend([
            create_mock_indexed_doc(
                risk_level='minimal',
                relevance_score=0.2,
                applicability=['housing'],
                provision_count=1,
                embedding_available=False
            ),
            create_mock_indexed_doc(
                risk_level='high',
                relevance_score=0.9,
                applicability=['employment', 'civil_rights'],
                provision_count=6,
                embedding_available=True
            ),
            create_mock_indexed_doc(
                risk_level='medium',
                relevance_score=0.6,
                applicability=['consumer'],
                provision_count=3,
                embedding_available=True
            ),
            create_mock_indexed_doc(
                risk_level='high',
                relevance_score=0.8,
                applicability=['housing', 'civil_rights'],
                provision_count=5,
                embedding_available=False
            ),
        ])
        
        # Test all Batch 218 methods
        assert indexer.total_indexed_documents() == 4
        
        assert indexer.documents_by_risk_level('minimal') == 1
        assert indexer.documents_by_risk_level('high') == 2
        assert indexer.documents_by_risk_level('medium') == 1
        
        dist = indexer.risk_level_distribution()
        assert dist == {'minimal': 1, 'high': 2, 'medium': 1}
        
        # Average relevance: (0.2 + 0.9 + 0.6 + 0.8) / 4 = 0.625
        assert abs(indexer.average_relevance_score() - 0.625) < 0.01
        
        assert abs(indexer.maximum_relevance_score() - 0.9) < 0.01
        
        assert indexer.documents_by_applicability('housing') == 2
        assert indexer.documents_by_applicability('employment') == 1
        assert indexer.documents_by_applicability('civil_rights') == 2
        assert indexer.documents_by_applicability('consumer') == 1
        
        app_dist = indexer.applicability_distribution()
        assert app_dist == {'housing': 2, 'employment': 1, 'civil_rights': 2, 'consumer': 1}
        
        # Average provisions: (1 + 6 + 3 + 5) / 4 = 3.75
        assert abs(indexer.average_legal_provisions() - 3.75) < 0.01
        
        # High risk percentage: 2 out of 4 = 50%
        assert abs(indexer.high_risk_documents_percentage() - 50.0) < 0.01
        
        # 2 out of 4 have embeddings
        assert indexer.documents_with_embeddings() == 2
