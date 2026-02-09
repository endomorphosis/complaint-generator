"""
Tests for seed generation, decision trees, prompt templates, and response parsers.
"""

import pytest
import json
import tempfile
from pathlib import Path

from complaint_analysis.seed_generator import SeedGenerator
from complaint_analysis.decision_trees import (
    DecisionTreeGenerator,
    DecisionTree
)
from complaint_analysis.prompt_templates import (
    PromptTemplate,
    PromptLibrary,
    ReturnFormat
)
from complaint_analysis.response_parsers import (
    JSONResponseParser,
    StructuredTextParser,
    EntityParser,
    RelationshipParser,
    QuestionParser,
    ClaimParser,
    StateFileIngester,
    ResponseParserFactory
)


class TestSeedGenerator:
    """Tests for SeedGenerator."""
    
    def test_initialization(self):
        """Test seed generator initializes templates."""
        generator = SeedGenerator()
        assert len(generator.templates) > 0
        
    def test_housing_templates(self):
        """Test housing templates are generated."""
        generator = SeedGenerator()
        templates = generator.list_templates(category='housing')
        assert len(templates) > 0
        assert any(t.type == 'housing_discrimination' for t in templates)
    
    def test_employment_templates(self):
        """Test employment templates are generated."""
        generator = SeedGenerator()
        templates = generator.list_templates(category='employment')
        assert len(templates) > 0
        assert any(t.type == 'employment_discrimination' for t in templates)
    
    def test_template_instantiation(self):
        """Test template can be instantiated with values."""
        generator = SeedGenerator()
        template = generator.list_templates(category='consumer')[0]
        
        values = {
            'business_name': 'Acme Corp',
            'product_or_service': 'Widget',
            'fraud_type': 'Misrepresentation'
        }
        
        seed = template.instantiate(values)
        assert seed['type'] == template.type
        assert seed['key_facts']['business_name'] == 'Acme Corp'
    
    def test_missing_required_fields(self):
        """Test error when required fields are missing."""
        generator = SeedGenerator()
        template = generator.list_templates()[0]
        
        with pytest.raises(ValueError, match="Missing required fields"):
            template.instantiate({})
    
    def test_get_template_by_id(self):
        """Test getting template by ID."""
        generator = SeedGenerator()
        templates = generator.list_templates()
        template = templates[0]
        
        retrieved = generator.get_template(template.id)
        assert retrieved == template
    
    def test_generate_seed(self):
        """Test generating a seed complaint."""
        generator = SeedGenerator()
        template_id = list(generator.templates.keys())[0]
        template = generator.templates[template_id]
        
        # Create values for all required fields
        values = {field: f"test_{field}" for field in template.required_fields}
        
        seed = generator.generate_seed(template_id, values)
        assert seed['template_id'] == template_id
        assert 'keywords' in seed
        assert 'legal_patterns' in seed


class TestDecisionTreeGenerator:
    """Tests for DecisionTreeGenerator."""
    
    def test_initialization(self):
        """Test decision tree generator initializes."""
        generator = DecisionTreeGenerator()
        assert generator.trees == {}
    
    def test_generate_housing_tree(self):
        """Test generating housing decision tree."""
        generator = DecisionTreeGenerator()
        tree = generator.generate_tree('housing')
        
        assert tree.complaint_type == 'housing'
        assert tree.category == 'housing'
        assert len(tree.questions) > 0
        assert len(tree.root_questions) > 0
    
    def test_generate_employment_tree(self):
        """Test generating employment decision tree."""
        generator = DecisionTreeGenerator()
        tree = generator.generate_tree('employment')
        
        assert tree.complaint_type == 'employment'
        assert tree.category == 'employment'
        assert len(tree.questions) > 0
    
    def test_tree_serialization(self):
        """Test decision tree serialization."""
        generator = DecisionTreeGenerator()
        tree = generator.generate_tree('housing')
        
        tree_dict = tree.to_dict()
        assert 'complaint_type' in tree_dict
        assert 'questions' in tree_dict
        
        # Test deserialization
        restored = DecisionTree.from_dict(tree_dict)
        assert restored.complaint_type == tree.complaint_type
        assert len(restored.questions) == len(tree.questions)
    
    def test_get_next_questions(self):
        """Test getting next questions based on answered fields."""
        generator = DecisionTreeGenerator()
        tree = generator.generate_tree('housing')
        
        # Initially, should get root questions
        next_q = tree.get_next_questions(set())
        assert len(next_q) > 0
        
        # After answering root questions, should get dependent questions
        answered = {q.field_name for q in next_q if q.id in tree.root_questions}
        next_q2 = tree.get_next_questions(answered)
        
        # Should have different questions
        field_names_1 = {q.field_name for q in next_q}
        field_names_2 = {q.field_name for q in next_q2}
        assert field_names_1 != field_names_2
    
    def test_save_and_load_tree(self):
        """Test saving and loading decision trees."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = DecisionTreeGenerator(output_dir=tmpdir)
            tree = generator.generate_tree('consumer')
            generator.save_tree(tree, 'consumer')
            
            # Check file was created
            tree_file = Path(tmpdir) / 'consumer_tree.json'
            assert tree_file.exists()
            
            # Load it back
            loaded = generator.load_tree('consumer')
            assert loaded.complaint_type == tree.complaint_type
            assert len(loaded.questions) == len(tree.questions)
    
    def test_generate_all_trees(self):
        """Test generating all trees."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = DecisionTreeGenerator(output_dir=tmpdir)
            generator.generate_all_trees()
            
            assert len(generator.trees) > 0
            
            # Check files were created
            json_files = list(Path(tmpdir).glob('*.json'))
            assert len(json_files) > 0


class TestPromptTemplates:
    """Tests for prompt templates."""
    
    def test_prompt_template_creation(self):
        """Test creating a prompt template."""
        template = PromptTemplate(
            name='test',
            system_prompt='You are a test assistant',
            return_format='Return JSON',
            return_format_type=ReturnFormat.JSON,
            warnings=['Warning 1'],
            payload_template='Process: {data}'
        )
        
        assert template.name == 'test'
        assert len(template.warnings) == 1
    
    def test_prompt_formatting(self):
        """Test formatting a prompt."""
        template = PromptTemplate(
            name='test',
            system_prompt='You are a test assistant',
            return_format='Return JSON',
            return_format_type=ReturnFormat.JSON,
            warnings=['Do not hallucinate'],
            payload_template='Process this: {data}'
        )
        
        formatted = template.format({'data': 'test data'})
        assert 'SYSTEM PROMPT' in formatted
        assert 'RETURN FORMAT' in formatted
        assert 'WARNINGS' in formatted
        assert 'PAYLOAD' in formatted
        assert 'test data' in formatted
    
    def test_prompt_library(self):
        """Test prompt library initialization."""
        library = PromptLibrary()
        assert len(library.templates) > 0
    
    def test_get_template(self):
        """Test getting template from library."""
        library = PromptLibrary()
        template = library.get_template('extract_entities')
        assert template is not None
        assert template.name == 'extract_entities'
    
    def test_format_prompt(self):
        """Test formatting prompt from library."""
        library = PromptLibrary()
        formatted = library.format_prompt('extract_entities', {
            'complaint_text': 'Test complaint'
        })
        assert 'Test complaint' in formatted
        assert 'SYSTEM PROMPT' in formatted
    
    def test_list_templates(self):
        """Test listing all templates."""
        library = PromptLibrary()
        templates = library.list_templates()
        assert len(templates) > 0
        assert 'extract_entities' in templates
        assert 'generate_questions' in templates


class TestResponseParsers:
    """Tests for response parsers."""
    
    def test_json_parser(self):
        """Test JSON response parser."""
        parser = JSONResponseParser()
        response = '{"entities": [{"text": "John", "type": "person"}]}'
        
        parsed = parser.parse(response)
        assert parsed.success
        assert len(parsed.errors) == 0
        assert 'entities' in parsed.data
    
    def test_json_parser_with_markdown(self):
        """Test JSON parser with markdown code blocks."""
        parser = JSONResponseParser()
        response = '''```json
{
  "entities": [
    {"text": "John", "type": "person"}
  ]
}
```'''
        
        parsed = parser.parse(response)
        assert parsed.success
        assert 'entities' in parsed.data
    
    def test_json_parser_invalid(self):
        """Test JSON parser with invalid JSON."""
        parser = JSONResponseParser()
        response = '{invalid json}'
        
        parsed = parser.parse(response)
        assert not parsed.success
        assert len(parsed.errors) > 0
    
    def test_structured_text_parser(self):
        """Test structured text parser."""
        parser = StructuredTextParser()
        response = '''Preamble text

## Section 1
Content 1

## Section 2
Content 2'''
        
        parsed = parser.parse(response)
        assert parsed.success
        # The parser splits on section headers, so first section becomes preamble
        assert 'preamble' in parsed.data or 'Section 1' in parsed.data
        assert 'Section 2' in parsed.data
    
    def test_entity_parser(self):
        """Test entity parser."""
        parser = EntityParser()
        response = '''{"entities": [
            {"text": "John Doe", "type": "person", "role": "complainant", "confidence": 0.9}
        ]}'''
        
        parsed = parser.parse(response)
        assert parsed.success
        assert len(parsed.data['entities']) == 1
        assert parsed.data['entities'][0]['text'] == 'John Doe'
    
    def test_relationship_parser(self):
        """Test relationship parser."""
        parser = RelationshipParser()
        response = '''{"relationships": [
            {"source": "John", "target": "Acme Corp", "type": "employed_by", "confidence": 0.95}
        ]}'''
        
        parsed = parser.parse(response)
        assert parsed.success
        assert len(parsed.data['relationships']) == 1
    
    def test_question_parser(self):
        """Test question parser."""
        parser = QuestionParser()
        response = '''{"questions": [
            {"question": "What is your name?", "field": "name", "priority": "high", "reasoning": "Required"}
        ]}'''
        
        parsed = parser.parse(response)
        assert parsed.success
        assert len(parsed.data['questions']) == 1
    
    def test_claim_parser(self):
        """Test claim parser."""
        parser = ClaimParser()
        response = '''{"claims": [
            {
                "claim_type": "discrimination",
                "legal_basis": "Title VII",
                "supporting_facts": ["fact1", "fact2"],
                "confidence": 0.8
            }
        ]}'''
        
        parsed = parser.parse(response)
        assert parsed.success
        assert len(parsed.data['claims']) == 1
    
    def test_parser_factory(self):
        """Test response parser factory."""
        parser = ResponseParserFactory.get_parser('json')
        assert isinstance(parser, JSONResponseParser)
        
        parser = ResponseParserFactory.get_parser('entities')
        assert isinstance(parser, EntityParser)
        
        with pytest.raises(ValueError):
            ResponseParserFactory.get_parser('invalid')


class TestStateFileIngester:
    """Tests for statefile ingester."""
    
    def test_ingest_entities(self):
        """Test ingesting entities to statefile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ingester = StateFileIngester(tmpdir)
            
            parser = EntityParser()
            response = '''{"entities": [
                {"text": "John", "type": "person", "confidence": 0.9}
            ]}'''
            parsed = parser.parse(response)
            
            success = ingester.ingest_entities(parsed, 'test_session')
            assert success
            
            # Check file was created
            kg_file = Path(tmpdir) / 'test_session_knowledge_graph.json'
            assert kg_file.exists()
            
            # Check content
            with open(kg_file) as f:
                kg = json.load(f)
            assert len(kg['entities']) == 1
    
    def test_ingest_relationships(self):
        """Test ingesting relationships to statefile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ingester = StateFileIngester(tmpdir)
            
            parser = RelationshipParser()
            response = '''{"relationships": [
                {"source": "A", "target": "B", "type": "knows", "confidence": 0.8}
            ]}'''
            parsed = parser.parse(response)
            
            success = ingester.ingest_relationships(parsed, 'test_session')
            assert success
            
            kg_file = Path(tmpdir) / 'test_session_knowledge_graph.json'
            assert kg_file.exists()
    
    def test_ingest_claims(self):
        """Test ingesting claims to statefile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ingester = StateFileIngester(tmpdir)
            
            parser = ClaimParser()
            response = '''{"claims": [
                {"claim_type": "test", "legal_basis": "statute", "supporting_facts": [], "confidence": 0.7}
            ]}'''
            parsed = parser.parse(response)
            
            success = ingester.ingest_claims(parsed, 'test_session')
            assert success
            
            dg_file = Path(tmpdir) / 'test_session_dependency_graph.json'
            assert dg_file.exists()
    
    def test_ingest_summary(self):
        """Test ingesting summary to statefile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ingester = StateFileIngester(tmpdir)
            
            parser = StructuredTextParser()
            response = '''## Summary
Test summary content'''
            parsed = parser.parse(response)
            
            success = ingester.ingest_summary(parsed, 'test_session')
            assert success
            
            summary_file = Path(tmpdir) / 'test_session_summary.json'
            assert summary_file.exists()
    
    def test_ingest_multiple_times(self):
        """Test ingesting multiple times appends data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ingester = StateFileIngester(tmpdir)
            
            # Ingest first batch
            parser = EntityParser()
            response1 = '''{"entities": [{"text": "A", "type": "person", "confidence": 0.9}]}'''
            parsed1 = parser.parse(response1)
            ingester.ingest_entities(parsed1, 'test_session')
            
            # Ingest second batch
            response2 = '''{"entities": [{"text": "B", "type": "person", "confidence": 0.8}]}'''
            parsed2 = parser.parse(response2)
            ingester.ingest_entities(parsed2, 'test_session')
            
            # Check both entities are present
            kg_file = Path(tmpdir) / 'test_session_knowledge_graph.json'
            with open(kg_file) as f:
                kg = json.load(f)
            assert len(kg['entities']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
