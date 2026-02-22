"""
Unit tests for Batch 217: DecisionTreeGenerator analysis methods.

Tests the 10 decision tree management and statistics methods added to DecisionTreeGenerator.
"""

import pytest
from complaint_analysis.decision_trees import (
    DecisionTreeGenerator,
    DecisionTree,
    QuestionNode
)


@pytest.fixture
def generator():
    """Create a DecisionTreeGenerator instance for testing."""
    return DecisionTreeGenerator()


def create_question_node(id='q1', question='Test?', field_name='test_field',
                         required=True):
    """Helper to create a QuestionNode for testing."""
    return QuestionNode(
        id=id,
        question=question,
        field_name=field_name,
        required=required
    )


def create_tree(complaint_type='test_type', category='test_category',
                num_questions=3, num_required=2, num_optional=1):
    """Helper to create a DecisionTree for testing."""
    questions = {}
    for i in range(num_questions):
        qid = f'q{i+1}'
        questions[qid] = create_question_node(
            id=qid,
            question=f'Question {i+1}?',
            field_name=f'field_{i+1}'
        )
    
    required_fields = {f'field_{i+1}' for i in range(num_required)}
    optional_fields = {f'field_{i+1}' for i in range(num_required, num_required + num_optional)}
    
    return DecisionTree(
        complaint_type=complaint_type,
        category=category,
        description='Test tree',
        root_questions=['q1'],
        questions=questions,
        required_fields=required_fields,
        optional_fields=optional_fields
    )


# ============================================================================ #
# Test total_trees()
# ============================================================================ #

class TestTotalTrees:
    def test_no_trees(self, generator):
        assert generator.total_trees() == 0
    
    def test_single_tree(self, generator):
        generator.trees['employment_discrimination'] = create_tree('employment_discrimination')
        assert generator.total_trees() == 1
    
    def test_multiple_trees(self, generator):
        generator.trees['housing'] = create_tree('housing')
        generator.trees['employment'] = create_tree('employment')
        generator.trees['consumer'] = create_tree('consumer')
        assert generator.total_trees() == 3


# ============================================================================ #
# Test trees_by_category()
# ============================================================================ #

class TestTreesByCategory:
    def test_no_trees(self, generator):
        assert generator.trees_by_category('civil_rights') == 0
    
    def test_no_matching_category(self, generator):
        generator.trees['t1'] = create_tree('t1', category='employment')
        assert generator.trees_by_category('housing') == 0
    
    def test_single_category(self, generator):
        generator.trees['t1'] = create_tree('t1', category='civil_rights')
        assert generator.trees_by_category('civil_rights') == 1
    
    def test_multiple_categories(self, generator):
        generator.trees['t1'] = create_tree('t1', category='employment')
        generator.trees['t2'] = create_tree('t2', category='housing')
        generator.trees['t3'] = create_tree('t3', category='employment')
        
        assert generator.trees_by_category('employment') == 2
        assert generator.trees_by_category('housing') == 1


# ============================================================================ #
# Test category_distribution()
# ============================================================================ #

class TestCategoryDistribution:
    def test_no_trees(self, generator):
        assert generator.category_distribution() == {}
    
    def test_single_category(self, generator):
        generator.trees['t1'] = create_tree('t1', category='housing')
        generator.trees['t2'] = create_tree('t2', category='housing')
        assert generator.category_distribution() == {'housing': 2}
    
    def test_multiple_categories(self, generator):
        generator.trees['t1'] = create_tree('t1', category='employment')
        generator.trees['t2'] = create_tree('t2', category='housing')
        generator.trees['t3'] = create_tree('t3', category='employment')
        generator.trees['t4'] = create_tree('t4', category='consumer')
        
        dist = generator.category_distribution()
        assert dist == {'employment': 2, 'housing': 1, 'consumer': 1}


# ============================================================================ #
# Test total_questions()
# ============================================================================ #

class TestTotalQuestions:
    def test_no_trees(self, generator):
        assert generator.total_questions() == 0
    
    def test_single_tree(self, generator):
        generator.trees['t1'] = create_tree('t1', num_questions=5)
        assert generator.total_questions() == 5
    
    def test_multiple_trees(self, generator):
        generator.trees['t1'] = create_tree('t1', num_questions=3)
        generator.trees['t2'] = create_tree('t2', num_questions=4)
        generator.trees['t3'] = create_tree('t3', num_questions=2)
        # Total: 3 + 4 + 2 = 9
        assert generator.total_questions() == 9


# ============================================================================ #
# Test average_questions_per_tree()
# ============================================================================ #

class TestAverageQuestionsPerTree:
    def test_no_trees(self, generator):
        assert generator.average_questions_per_tree() == 0.0
    
    def test_single_tree(self, generator):
        generator.trees['t1'] = create_tree('t1', num_questions=6)
        assert generator.average_questions_per_tree() == 6.0
    
    def test_multiple_trees(self, generator):
        generator.trees['t1'] = create_tree('t1', num_questions=2)
        generator.trees['t2'] = create_tree('t2', num_questions=4)
        generator.trees['t3'] = create_tree('t3', num_questions=6)
        # Average: (2 + 4 + 6) / 3 = 4.0
        assert abs(generator.average_questions_per_tree() - 4.0) < 0.01


# ============================================================================ #
# Test maximum_questions_count()
# ============================================================================ #

class TestMaximumQuestionsCount:
    def test_no_trees(self, generator):
        assert generator.maximum_questions_count() == 0
    
    def test_single_tree(self, generator):
        generator.trees['t1'] = create_tree('t1', num_questions=7)
        assert generator.maximum_questions_count() == 7
    
    def test_multiple_trees(self, generator):
        generator.trees['t1'] = create_tree('t1', num_questions=3)
        generator.trees['t2'] = create_tree('t2', num_questions=8)
        generator.trees['t3'] = create_tree('t3', num_questions=5)
        assert generator.maximum_questions_count() == 8


# ============================================================================ #
# Test total_required_fields()
# ============================================================================ #

class TestTotalRequiredFields:
    def test_no_trees(self, generator):
        assert generator.total_required_fields() == 0
    
    def test_single_tree(self, generator):
        generator.trees['t1'] = create_tree('t1', num_required=4)
        assert generator.total_required_fields() == 4
    
    def test_multiple_trees(self, generator):
        generator.trees['t1'] = create_tree('t1', num_required=2)
        generator.trees['t2'] = create_tree('t2', num_required=3)
        generator.trees['t3'] = create_tree('t3', num_required=5)
        # Total: 2 + 3 + 5 = 10
        assert generator.total_required_fields() == 10


# ============================================================================ #
# Test average_required_fields_per_tree()
# ============================================================================ #

class TestAverageRequiredFieldsPerTree:
    def test_no_trees(self, generator):
        assert generator.average_required_fields_per_tree() == 0.0
    
    def test_single_tree(self, generator):
        generator.trees['t1'] = create_tree('t1', num_required=5)
        assert generator.average_required_fields_per_tree() == 5.0
    
    def test_multiple_trees(self, generator):
        generator.trees['t1'] = create_tree('t1', num_required=1)
        generator.trees['t2'] = create_tree('t2', num_required=2)
        generator.trees['t3'] = create_tree('t3', num_required=3)
        # Average: (1 + 2 + 3) / 3 = 2.0
        assert abs(generator.average_required_fields_per_tree() - 2.0) < 0.01


# ============================================================================ #
# Test trees_with_root_questions()
# ============================================================================ #

class TestTreesWithRootQuestions:
    def test_no_trees(self, generator):
        assert generator.trees_with_root_questions() == 0
    
    def test_no_root_questions(self, generator):
        tree = create_tree('t1')
        tree.root_questions = []
        generator.trees['t1'] = tree
        assert generator.trees_with_root_questions() == 0
    
    def test_all_have_root_questions(self, generator):
        generator.trees['t1'] = create_tree('t1')  # Has root_questions by default
        generator.trees['t2'] = create_tree('t2')
        assert generator.trees_with_root_questions() == 2
    
    def test_mixed(self, generator):
        tree1 = create_tree('t1')
        tree1.root_questions = ['q1']
        generator.trees['t1'] = tree1
        
        tree2 = create_tree('t2')
        tree2.root_questions = []
        generator.trees['t2'] = tree2
        
        generator.trees['t3'] = create_tree('t3')  # Has root_questions
        
        assert generator.trees_with_root_questions() == 2


# ============================================================================ #
# Test tree_coverage_percentage()
# ============================================================================ #

class TestTreeCoveragePercentage:
    def test_no_complaint_types(self, generator):
        assert generator.tree_coverage_percentage([]) == 0.0
    
    def test_no_trees(self, generator):
        types = ['housing', 'employment', 'consumer']
        assert generator.tree_coverage_percentage(types) == 0.0
    
    def test_full_coverage(self, generator):
        types = ['housing', 'employment']
        generator.trees['housing'] = create_tree('housing')
        generator.trees['employment'] = create_tree('employment')
        assert generator.tree_coverage_percentage(types) == 100.0
    
    def test_partial_coverage(self, generator):
        types = ['housing', 'employment', 'consumer', 'healthcare']
        generator.trees['housing'] = create_tree('housing')
        generator.trees['employment'] = create_tree('employment')
        # 2 out of 4 = 50%
        assert abs(generator.tree_coverage_percentage(types) - 50.0) < 0.01


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch217Integration:
    def test_comprehensive_decision_tree_analysis(self, generator):
        """Test that all Batch 217 methods work together correctly."""
        # Create trees with varying characteristics
        generator.trees['housing_discrimination'] = create_tree(
            'housing_discrimination',
            category='housing',
            num_questions=8,
            num_required=5,
            num_optional=3
        )
        generator.trees['employment_discrimination'] = create_tree(
            'employment_discrimination',
            category='employment',
            num_questions=10,
            num_required=6,
            num_optional=4
        )
        generator.trees['consumer_fraud'] = create_tree(
            'consumer_fraud',
            category='consumer',
            num_questions=6,
            num_required=4,
            num_optional=2
        )
        
        # Tree without root questions
        tree4 = create_tree('healthcare_malpractice', category='healthcare',
                           num_questions=12, num_required=8, num_optional=4)
        tree4.root_questions = []
        generator.trees['healthcare_malpractice'] = tree4
        
        # Test all Batch 217 methods
        assert generator.total_trees() == 4
        
        assert generator.trees_by_category('housing') == 1
        assert generator.trees_by_category('employment') == 1
        assert generator.trees_by_category('consumer') == 1
        assert generator.trees_by_category('healthcare') == 1
        
        dist = generator.category_distribution()
        assert dist == {'housing': 1, 'employment': 1, 'consumer': 1, 'healthcare': 1}
        
        # Total questions: 8 + 10 + 6 + 12 = 36
        assert generator.total_questions() == 36
        
        # Average questions: 36 / 4 = 9.0
        assert abs(generator.average_questions_per_tree() - 9.0) < 0.01
        
        assert generator.maximum_questions_count() == 12
        
        # Total required: 5 + 6 + 4 + 8 = 23
        assert generator.total_required_fields() == 23
        
        # Average required: 23 / 4 = 5.75
        assert abs(generator.average_required_fields_per_tree() - 5.75) < 0.01
        
        # 3 out of 4 have root questions
        assert generator.trees_with_root_questions() == 3
        
        # Coverage test
        all_types = [
            'housing_discrimination',
            'employment_discrimination',
            'consumer_fraud',
            'healthcare_malpractice',
            'tax_evasion'  # Not generated
        ]
        # 4 out of 5 = 80%
        assert abs(generator.tree_coverage_percentage(all_types) - 80.0) < 0.01
