"""
Unit tests for Batch 210: SeedGenerator analysis methods.

Tests the 10 template analysis and statistics methods added to SeedGenerator.
"""

import pytest
from complaint_analysis.seed_generator import SeedGenerator, SeedComplaintTemplate


@pytest.fixture
def seed_generator():
    """Create a SeedGenerator instance for testing."""
    gen = SeedGenerator()
    # Clear templates for controlled testing
    gen.templates = {}
    return gen


def create_template(template_id, category='housing', complaint_type='housing',
                   required_fields=None, optional_fields=None):
    """Helper to create a SeedComplaintTemplate."""
    if required_fields is None:
        required_fields = []
    if optional_fields is None:
        optional_fields = []
    
    return SeedComplaintTemplate(
        id=template_id,
        type=complaint_type,
        category=category,
        description=f"Description for {template_id}",
        key_facts_template={'fact': 'value'},
        required_fields=required_fields,
        optional_fields=optional_fields
    )


# ============================================================================ #
# Test total_templates()
# ============================================================================ #

class TestTotalTemplates:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.total_templates() == 0
    
    def test_single_template(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1')
        assert seed_generator.total_templates() == 1
    
    def test_multiple_templates(self, seed_generator):
        for i in range(10):
            seed_generator.templates[f't{i}'] = create_template(f't{i}')
        assert seed_generator.total_templates() == 10


# ============================================================================ #
# Test templates_by_category()
# ============================================================================ #

class TestTemplatesByCategory:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.templates_by_category('housing') == 0
    
    def test_no_matching_category(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='housing')
        assert seed_generator.templates_by_category('employment') == 0
    
    def test_single_category(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='housing')
        seed_generator.templates['t2'] = create_template('t2', category='housing')
        assert seed_generator.templates_by_category('housing') == 2
    
    def test_mixed_categories(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='housing')
        seed_generator.templates['t2'] = create_template('t2', category='employment')
        seed_generator.templates['t3'] = create_template('t3', category='housing')
        assert seed_generator.templates_by_category('housing') == 2
        assert seed_generator.templates_by_category('employment') == 1


# ============================================================================ #
# Test category_distribution()
# ============================================================================ #

class TestCategoryDistribution:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.category_distribution() == {}
    
    def test_single_category(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='housing')
        seed_generator.templates['t2'] = create_template('t2', category='housing')
        dist = seed_generator.category_distribution()
        assert dist == {'housing': 2}
    
    def test_multiple_categories(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='housing')
        seed_generator.templates['t2'] = create_template('t2', category='employment')
        seed_generator.templates['t3'] = create_template('t3', category='housing')
        seed_generator.templates['t4'] = create_template('t4', category='civil_rights')
        dist = seed_generator.category_distribution()
        assert dist == {'housing': 2, 'employment': 1, 'civil_rights': 1}


# ============================================================================ #
# Test most_common_category()
# ============================================================================ #

class TestMostCommonCategory:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.most_common_category() == 'none'
    
    def test_single_category(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='consumer')
        assert seed_generator.most_common_category() == 'consumer'
    
    def test_clear_winner(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', category='housing')
        seed_generator.templates['t2'] = create_template('t2', category='housing')
        seed_generator.templates['t3'] = create_template('t3', category='housing')
        seed_generator.templates['t4'] = create_template('t4', category='employment')
        assert seed_generator.most_common_category() == 'housing'


# ============================================================================ #
# Test type_distribution()
# ============================================================================ #

class TestTypeDistribution:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.type_distribution() == {}
    
    def test_single_type(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', complaint_type='housing')
        seed_generator.templates['t2'] = create_template('t2', complaint_type='housing')
        dist = seed_generator.type_distribution()
        assert dist == {'housing': 2}
    
    def test_multiple_types(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', complaint_type='housing')
        seed_generator.templates['t2'] = create_template('t2', complaint_type='employment')
        seed_generator.templates['t3'] = create_template('t3', complaint_type='housing')
        seed_generator.templates['t4'] = create_template('t4', complaint_type='dei')
        dist = seed_generator.type_distribution()
        assert dist == {'housing': 2, 'employment': 1, 'dei': 1}


# ============================================================================ #
# Test templates_with_required_fields()
# ============================================================================ #

class TestTemplatesWithRequiredFields:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.templates_with_required_fields() == 0
    
    def test_no_required_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', required_fields=[])
        seed_generator.templates['t2'] = create_template('t2', required_fields=[])
        assert seed_generator.templates_with_required_fields() == 0
    
    def test_all_have_required_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', required_fields=['name', 'address'])
        seed_generator.templates['t2'] = create_template('t2', required_fields=['date'])
        assert seed_generator.templates_with_required_fields() == 2
    
    def test_mixed_required_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', required_fields=['name'])
        seed_generator.templates['t2'] = create_template('t2', required_fields=[])
        seed_generator.templates['t3'] = create_template('t3', required_fields=['date', 'location'])
        assert seed_generator.templates_with_required_fields() == 2


# ============================================================================ #
# Test average_required_fields_per_template()
# ============================================================================ #

class TestAverageRequiredFieldsPerTemplate:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.average_required_fields_per_template() == 0.0
    
    def test_no_required_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', required_fields=[])
        seed_generator.templates['t2'] = create_template('t2', required_fields=[])
        assert seed_generator.average_required_fields_per_template() == 0.0
    
    def test_uniform_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', required_fields=['name', 'date'])
        seed_generator.templates['t2'] = create_template('t2', required_fields=['addr', 'phone'])
        assert seed_generator.average_required_fields_per_template() == 2.0
    
    def test_varied_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', required_fields=['name'])
        seed_generator.templates['t2'] = create_template('t2', required_fields=['a', 'b', 'c'])
        seed_generator.templates['t3'] = create_template('t3', required_fields=[])
        avg = seed_generator.average_required_fields_per_template()
        # Total: 1 + 3 + 0 = 4, avg = 4/3
        assert abs(avg - (4/3)) < 0.01


# ============================================================================ #
# Test templates_with_optional_fields()
# ============================================================================ #

class TestTemplatesWithOptionalFields:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.templates_with_optional_fields() == 0
    
    def test_no_optional_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', optional_fields=[])
        seed_generator.templates['t2'] = create_template('t2', optional_fields=[])
        assert seed_generator.templates_with_optional_fields() == 0
    
    def test_all_have_optional_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', optional_fields=['email'])
        seed_generator.templates['t2'] = create_template('t2', optional_fields=['fax', 'mobile'])
        assert seed_generator.templates_with_optional_fields() == 2
    
    def test_mixed_optional_fields(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', optional_fields=['email'])
        seed_generator.templates['t2'] = create_template('t2', optional_fields=[])
        seed_generator.templates['t3'] = create_template('t3', optional_fields=['notes'])
        assert seed_generator.templates_with_optional_fields() == 2


# ============================================================================ #
# Test has_template_for_type()
# ============================================================================ #

class TestHasTemplateForType:
    def test_empty_generator(self, seed_generator):
        assert seed_generator.has_template_for_type('housing') is False
    
    def test_has_type(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', complaint_type='housing')
        assert seed_generator.has_template_for_type('housing') is True
    
    def test_does_not_have_type(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', complaint_type='housing')
        assert seed_generator.has_template_for_type('employment') is False
    
    def test_multiple_templates_same_type(self, seed_generator):
        seed_generator.templates['t1'] = create_template('t1', complaint_type='housing')
        seed_generator.templates['t2'] = create_template('t2', complaint_type='housing')
        seed_generator.templates['t3'] = create_template('t3', complaint_type='employment')
        assert seed_generator.has_template_for_type('housing') is True
        assert seed_generator.has_template_for_type('employment') is True
        assert seed_generator.has_template_for_type('consumer') is False


# ============================================================================ #
# Test template_coverage_score()
# ============================================================================ #

class TestTemplateCoverageScore:
    def test_empty_generator(self, seed_generator):
        # This depends on registered types, but should handle empty case
        score = seed_generator.template_coverage_score()
        assert 0.0 <= score <= 1.0
    
    def test_with_templates_for_registered_types(self, seed_generator):
        # Add templates for some registered types
        seed_generator.templates['t1'] = create_template('t1', complaint_type='housing')
        seed_generator.templates['t2'] = create_template('t2', complaint_type='employment')
        score = seed_generator.template_coverage_score()
        # Should be between 0 and 1
        assert 0.0 <= score <= 1.0


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch210Integration:
    def test_comprehensive_seed_generator_analysis(self, seed_generator):
        """Test that all Batch 210 methods work together correctly."""
        # Populate with realistic templates
        seed_generator.templates['housing1'] = create_template(
            'housing1',
            category='housing',
            complaint_type='housing',
            required_fields=['landlord_name', 'property_address', 'violation_date'],
            optional_fields=['witness_name', 'evidence']
        )
        seed_generator.templates['housing2'] = create_template(
            'housing2',
            category='housing',
            complaint_type='housing',
            required_fields=['tenant_name', 'lease_date'],
            optional_fields=[]
        )
        seed_generator.templates['employment1'] = create_template(
            'employment1',
            category='employment',
            complaint_type='employment',
            required_fields=['employer_name', 'incident_date', 'claim_type'],
            optional_fields=['supervisor_name']
        )
        seed_generator.templates['dei1'] = create_template(
            'dei1',
            category='employment',
            complaint_type='dei',
            required_fields=['protected_class'],
            optional_fields=['comparator', 'witnesses']
        )
        
        # Test all methods
        assert seed_generator.total_templates() == 4
        assert seed_generator.templates_by_category('housing') == 2
        assert seed_generator.templates_by_category('employment') == 2
        
        cat_dist = seed_generator.category_distribution()
        assert cat_dist == {'housing': 2, 'employment': 2}
        assert seed_generator.most_common_category() in ['housing', 'employment']
        
        type_dist = seed_generator.type_distribution()
        assert type_dist == {'housing': 2, 'employment': 1, 'dei': 1}
        
        assert seed_generator.templates_with_required_fields() == 4
        avg_required = seed_generator.average_required_fields_per_template()
        # Total: 3 + 2 + 3 + 1 = 9, avg = 9/4 = 2.25
        assert abs(avg_required - 2.25) < 0.01
        
        assert seed_generator.templates_with_optional_fields() == 3  # housing2 has none
        
        assert seed_generator.has_template_for_type('housing') is True
        assert seed_generator.has_template_for_type('employment') is True
        assert seed_generator.has_template_for_type('dei') is True
        assert seed_generator.has_template_for_type('consumer') is False
        
        coverage = seed_generator.template_coverage_score()
        assert 0.0 <= coverage <= 1.0
