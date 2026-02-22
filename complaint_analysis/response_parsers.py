"""
Response Parsers

Parse LLM responses and ingest into statefiles.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Exception raised when parsing fails."""
    pass


@dataclass
class ParsedResponse:
    """Container for parsed LLM response."""
    data: Union[Dict[str, Any], List[Any], str]
    format_type: str
    success: bool
    errors: List[str]
    warnings: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'data': self.data,
            'format_type': self.format_type,
            'success': self.success,
            'errors': self.errors,
            'warnings': self.warnings
        }


class BaseResponseParser(ABC):
    """Base class for response parsers."""
    
    @abstractmethod
    def parse(self, response: str) -> ParsedResponse:
        """
        Parse an LLM response.
        
        Args:
            response: The raw response string
            
        Returns:
            ParsedResponse object
        """
        pass
    
    @abstractmethod
    def validate(self, parsed_data: Any) -> List[str]:
        """
        Validate parsed data.
        
        Args:
            parsed_data: The parsed data
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass


class JSONResponseParser(BaseResponseParser):
    """Parser for JSON responses."""
    
    def __init__(self, schema: Optional[Dict[str, Any]] = None):
        """
        Initialize JSON parser.
        
        Args:
            schema: Optional JSON schema for validation
        """
        self.schema = schema
    
    def parse(self, response: str) -> ParsedResponse:
        """Parse JSON response."""
        errors = []
        warnings = []
        data = None
        success = False
        
        try:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON object/array
                json_match = re.search(r'(\{.*\}|\[.*\])', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Validate
            validation_errors = self.validate(data)
            if validation_errors:
                errors.extend(validation_errors)
            else:
                success = True
                
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {str(e)}")
            logger.error(f"Failed to parse JSON response: {e}")
        except Exception as e:
            errors.append(f"Unexpected error: {str(e)}")
            logger.error(f"Unexpected error parsing response: {e}")
        
        return ParsedResponse(
            data=data,
            format_type='json',
            success=success,
            errors=errors,
            warnings=warnings
        )
    
    def validate(self, parsed_data: Any) -> List[str]:
        """Validate JSON data against schema if provided."""
        errors = []
        
        if self.schema is None:
            return errors
        
        # Simple validation - check required fields
        if 'required' in self.schema:
            if not isinstance(parsed_data, dict):
                errors.append("Expected object for schema validation")
                return errors
            
            for field in self.schema['required']:
                if field not in parsed_data:
                    errors.append(f"Missing required field: {field}")
        
        return errors


class StructuredTextParser(BaseResponseParser):
    """Parser for structured text responses."""
    
    def __init__(self, expected_sections: Optional[List[str]] = None):
        """
        Initialize structured text parser.
        
        Args:
            expected_sections: Optional list of expected section headers
        """
        self.expected_sections = expected_sections or []
    
    def parse(self, response: str) -> ParsedResponse:
        """Parse structured text response."""
        errors = []
        warnings = []
        data = {}
        success = False
        
        try:
            # Extract sections based on headers (##, **, etc.)
            # Pattern matches headers like "## Section" or "**Section:**"
            sections = re.split(r'\n(?:##|\*\*)\s*([^\n:*]+)[\s:*]*\n', response)
            
            if len(sections) > 1:
                # First element is text before any section
                if sections[0].strip():
                    data['preamble'] = sections[0].strip()
                
                # Process section pairs (header, content)
                for i in range(1, len(sections), 2):
                    if i + 1 < len(sections):
                        section_name = sections[i].strip()
                        section_content = sections[i + 1].strip()
                        data[section_name] = section_content
                
                success = True
            else:
                # No sections found, treat as single text block
                data['content'] = response.strip()
                success = True
            
            # Validate
            validation_errors = self.validate(data)
            if validation_errors:
                warnings.extend(validation_errors)
            
        except Exception as e:
            errors.append(f"Parsing error: {str(e)}")
            logger.error(f"Error parsing structured text: {e}")
        
        return ParsedResponse(
            data=data,
            format_type='structured_text',
            success=success,
            errors=errors,
            warnings=warnings
        )
    
    def validate(self, parsed_data: Dict[str, str]) -> List[str]:
        """Validate that expected sections are present."""
        errors = []
        
        if not self.expected_sections:
            return errors
        
        for section in self.expected_sections:
            if section not in parsed_data:
                errors.append(f"Missing expected section: {section}")
        
        return errors


class EntityParser(JSONResponseParser):
    """Specialized parser for entity extraction responses."""
    
    def __init__(self):
        """Initialize entity parser."""
        schema = {
            'required': ['entities'],
            'properties': {
                'entities': {
                    'type': 'array',
                    'items': {
                        'required': ['text', 'type'],
                        'properties': {
                            'text': {'type': 'string'},
                            'type': {'type': 'string'},
                            'role': {'type': 'string'},
                            'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}
                        }
                    }
                }
            }
        }
        super().__init__(schema)
    
    def validate(self, parsed_data: Any) -> List[str]:
        """Validate entity extraction data."""
        errors = super().validate(parsed_data)
        
        if not isinstance(parsed_data, dict):
            return errors
        
        if 'entities' not in parsed_data:
            return errors
        
        entities = parsed_data['entities']
        if not isinstance(entities, list):
            errors.append("'entities' must be a list")
            return errors
        
        for i, entity in enumerate(entities):
            if not isinstance(entity, dict):
                errors.append(f"Entity {i} must be an object")
                continue
            
            if 'text' not in entity or not entity['text']:
                errors.append(f"Entity {i} missing 'text' field")
            
            if 'type' not in entity or not entity['type']:
                errors.append(f"Entity {i} missing 'type' field")
            
            if 'confidence' in entity:
                conf = entity['confidence']
                if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                    errors.append(f"Entity {i} has invalid confidence value")
        
        return errors


class RelationshipParser(JSONResponseParser):
    """Specialized parser for relationship extraction responses."""
    
    def __init__(self):
        """Initialize relationship parser."""
        schema = {
            'required': ['relationships'],
            'properties': {
                'relationships': {
                    'type': 'array',
                    'items': {
                        'required': ['source', 'target', 'type'],
                        'properties': {
                            'source': {'type': 'string'},
                            'target': {'type': 'string'},
                            'type': {'type': 'string'},
                            'confidence': {'type': 'number'}
                        }
                    }
                }
            }
        }
        super().__init__(schema)


class QuestionParser(JSONResponseParser):
    """Specialized parser for question generation responses."""
    
    def __init__(self):
        """Initialize question parser."""
        schema = {
            'required': ['questions'],
            'properties': {
                'questions': {
                    'type': 'array',
                    'items': {
                        'required': ['question', 'field'],
                        'properties': {
                            'question': {'type': 'string'},
                            'field': {'type': 'string'},
                            'priority': {'type': 'string'},
                            'reasoning': {'type': 'string'}
                        }
                    }
                }
            }
        }
        super().__init__(schema)


class ClaimParser(JSONResponseParser):
    """Specialized parser for legal claim extraction responses."""
    
    def __init__(self):
        """Initialize claim parser."""
        schema = {
            'required': ['claims'],
            'properties': {
                'claims': {
                    'type': 'array',
                    'items': {
                        'required': ['claim_type', 'legal_basis'],
                        'properties': {
                            'claim_type': {'type': 'string'},
                            'legal_basis': {'type': 'string'},
                            'supporting_facts': {'type': 'array'},
                            'confidence': {'type': 'number'}
                        }
                    }
                }
            }
        }
        super().__init__(schema)


class StateFileIngester:
    """
    Ingest parsed responses into statefile format.
    
    Converts parsed LLM responses into the structured JSON format
    used by the statefiles system.
    """
    
    def __init__(self, statefiles_dir: str):
        """
        Initialize statefile ingester.
        
        Args:
            statefiles_dir: Directory where statefiles are stored
        """
        self.statefiles_dir = Path(statefiles_dir)
        self.statefiles_dir.mkdir(parents=True, exist_ok=True)
    
    def ingest_entities(self, parsed: ParsedResponse, session_id: str) -> bool:
        """
        Ingest entities into knowledge graph statefile.
        
        Args:
            parsed: Parsed entity extraction response
            session_id: Session identifier
            
        Returns:
            True if successful
        """
        if not parsed.success or 'entities' not in parsed.data:
            logger.error("Cannot ingest invalid entity data")
            return False
        
        statefile_path = self.statefiles_dir / f"{session_id}_knowledge_graph.json"
        
        # Load existing or create new
        if statefile_path.exists():
            with open(statefile_path, 'r') as f:
                kg = json.load(f)
        else:
            kg = {'entities': [], 'relationships': [], 'facts': []}
        
        # Add new entities
        for entity in parsed.data['entities']:
            kg['entities'].append(entity)
        
        # Save
        with open(statefile_path, 'w') as f:
            json.dump(kg, f, indent=2)
        
        logger.info(f"Ingested {len(parsed.data['entities'])} entities to {statefile_path}")
        return True
    
    def ingest_relationships(self, parsed: ParsedResponse, session_id: str) -> bool:
        """
        Ingest relationships into knowledge graph statefile.
        
        Args:
            parsed: Parsed relationship extraction response
            session_id: Session identifier
            
        Returns:
            True if successful
        """
        if not parsed.success or 'relationships' not in parsed.data:
            logger.error("Cannot ingest invalid relationship data")
            return False
        
        statefile_path = self.statefiles_dir / f"{session_id}_knowledge_graph.json"
        
        # Load existing or create new
        if statefile_path.exists():
            with open(statefile_path, 'r') as f:
                kg = json.load(f)
        else:
            kg = {'entities': [], 'relationships': [], 'facts': []}
        
        # Add new relationships
        for rel in parsed.data['relationships']:
            kg['relationships'].append(rel)
        
        # Save
        with open(statefile_path, 'w') as f:
            json.dump(kg, f, indent=2)
        
        logger.info(
            f"Ingested {len(parsed.data['relationships'])} relationships "
            f"to {statefile_path}"
        )
        return True
    
    def ingest_claims(self, parsed: ParsedResponse, session_id: str) -> bool:
        """
        Ingest claims into dependency graph statefile.
        
        Args:
            parsed: Parsed claim extraction response
            session_id: Session identifier
            
        Returns:
            True if successful
        """
        if not parsed.success or 'claims' not in parsed.data:
            logger.error("Cannot ingest invalid claim data")
            return False
        
        statefile_path = self.statefiles_dir / f"{session_id}_dependency_graph.json"
        
        # Load existing or create new
        if statefile_path.exists():
            with open(statefile_path, 'r') as f:
                dg = json.load(f)
        else:
            dg = {'claims': [], 'requirements': []}
        
        # Add new claims
        for claim in parsed.data['claims']:
            dg['claims'].append(claim)
        
        # Save
        with open(statefile_path, 'w') as f:
            json.dump(dg, f, indent=2)
        
        logger.info(f"Ingested {len(parsed.data['claims'])} claims to {statefile_path}")
        return True
    
    def ingest_summary(self, parsed: ParsedResponse, session_id: str) -> bool:
        """
        Ingest summary into statefile.
        
        Args:
            parsed: Parsed summary response
            session_id: Session identifier
            
        Returns:
            True if successful
        """
        if not parsed.success:
            logger.error("Cannot ingest invalid summary data")
            return False
        
        statefile_path = self.statefiles_dir / f"{session_id}_summary.json"
        
        # Save summary
        with open(statefile_path, 'w') as f:
            json.dump(parsed.data, f, indent=2)
        
        logger.info(f"Ingested summary to {statefile_path}")
        return True


class ResponseParserFactory:
    """Factory for creating appropriate parsers with caching and history tracking."""
    
    def __init__(self):
        """Initialize the parser factory with caching."""
        self._parser_instances = {}  # Cache parser instances
        self._parsing_history = []  # Track all parsing operations
        self._parse_success_count = 0  # Counter for successful parses
        self._parse_failure_count = 0  # Counter for failed parses
    
    def get_parser(self, parser_type: str) -> BaseResponseParser:
        """
        Get appropriate parser for response type with caching.
        
        Args:
            parser_type: Type of parser needed
            
        Returns:
            Parser instance (cached if already created)
        """
        # Return cached instance if available
        if parser_type in self._parser_instances:
            return self._parser_instances[parser_type]
        
        # Create new instance based on type
        parser_map = {
            'json': JSONResponseParser,
            'structured_text': StructuredTextParser,
            'entities': EntityParser,
            'relationships': RelationshipParser,
            'questions': QuestionParser,
            'claims': ClaimParser
        }
        
        if parser_type not in parser_map:
            raise ValueError(f"Unknown parser type: {parser_type}")
        
        # Create and cache the parser
        parser = parser_map[parser_type]()
        self._parser_instances[parser_type] = parser
        
        return parser
    
    def parse_with_tracking(self, response: str, parser_type: str) -> ParsedResponse:
        """
        Parse response and track the operation.
        
        Args:
            response: Raw response to parse
            parser_type: Type of parser to use
            
        Returns:
            ParsedResponse with tracking
        """
        parser = self.get_parser(parser_type)
        parsed = parser.parse(response)
        
        # Track the operation
        history_entry = {
            'parser_type': parser_type,
            'response_length': len(response),
            'success': parsed.success,
            'errors': len(parsed.errors),
            'warnings': len(parsed.warnings)
        }
        self._parsing_history.append(history_entry)
        
        # Update counters
        if parsed.success:
            self._parse_success_count += 1
        else:
            self._parse_failure_count += 1
        
        return parsed
    
    def total_parsing_operations(self) -> int:
        """Get total number of parsing operations.
        
        Returns:
            Count of all parse operations.
        """
        return len(self._parsing_history)
    
    def successful_parse_count(self) -> int:
        """Get count of successful parsing operations.
        
        Returns:
            Number of successful parses.
        """
        return self._parse_success_count
    
    def failed_parse_count(self) -> int:
        """Get count of failed parsing operations.
        
        Returns:
            Number of failed parses.
        """
        return self._parse_failure_count
    
    def success_rate(self) -> float:
        """Calculate success rate of parsing operations.
        
        Returns:
            Success rate (0.0 to 1.0), or 0.0 if no operations.
        """
        total = self.total_parsing_operations()
        if total == 0:
            return 0.0
        return self._parse_success_count / total
    
    def parser_type_distribution(self) -> Dict[str, int]:
        """Get distribution of parser types used.
        
        Returns:
            Dict mapping parser types to usage counts.
        """
        distribution = {}
        for entry in self._parsing_history:
            parser_type = entry['parser_type']
            distribution[parser_type] = distribution.get(parser_type, 0) + 1
        return distribution
    
    def average_response_length(self) -> float:
        """Calculate average response length across all operations.
        
        Returns:
            Mean response length, or 0.0 if no operations.
        """
        if not self._parsing_history:
            return 0.0
        total_length = sum(entry['response_length'] for entry in self._parsing_history)
        return total_length / len(self._parsing_history)
    
    def error_ratio(self) -> float:
        """Calculate ratio of operations with errors.
        
        Returns:
            Ratio of operations with errors (0.0 to 1.0).
        """
        if not self._parsing_history:
            return 0.0
        error_ops = sum(1 for entry in self._parsing_history if entry['errors'] > 0)
        return error_ops / len(self._parsing_history)
    
    def most_used_parser(self) -> str:
        """Find the most frequently used parser type.
        
        Returns:
            Parser type used most often, or 'none' if no operations.
        """
        dist = self.parser_type_distribution()
        if not dist:
            return 'none'
        return max(dist, key=dist.get)
    
    def clear_history(self) -> None:
        """Clear all parsing history and reset counters."""
        self._parsing_history.clear()
        self._parse_success_count = 0
        self._parse_failure_count = 0
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve parsing history.
        
        Args:
            limit: Optional limit on number of most recent entries to return
            
        Returns:
            List of history entries.
        """
        history = list(self._parsing_history)
        if limit is None:
            return history
        if limit <= 0:
            return []
        return history[-limit:]
    
    @staticmethod
    def create() -> 'ResponseParserFactory':
        """Create a new ResponseParserFactory instance."""
        return ResponseParserFactory()
