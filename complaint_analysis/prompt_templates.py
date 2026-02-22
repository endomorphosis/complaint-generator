"""
Prompt Templates

Structured prompt engineering with format: | system prompt | return format | warnings | payload |
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ReturnFormat(Enum):
    """Enumeration of supported return formats."""
    JSON = "json"
    STRUCTURED_TEXT = "structured_text"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"


@dataclass
class PromptTemplate:
    """
    Structured prompt template with four sections:
    1. System prompt - Role and context
    2. Return format - Expected output structure
    3. Warnings - Constraints and limitations
    4. Payload - Actual data/query
    """
    name: str
    system_prompt: str
    return_format: str
    return_format_type: ReturnFormat
    warnings: List[str] = field(default_factory=list)
    payload_template: str = ""
    
    def format(self, payload_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Format the complete prompt.
        
        Args:
            payload_data: Optional data to fill in the payload template
            
        Returns:
            Formatted prompt string
        """
        # Format payload if data provided
        payload = self.payload_template
        if payload_data:
            payload = self.payload_template.format(**payload_data)
        
        # Construct full prompt
        prompt_parts = [
            f"## SYSTEM PROMPT\n{self.system_prompt}",
            f"\n## RETURN FORMAT\n{self.return_format}",
        ]
        
        if self.warnings:
            warnings_text = "\n".join(f"- {w}" for w in self.warnings)
            prompt_parts.append(f"\n## WARNINGS\n{warnings_text}")
        
        prompt_parts.append(f"\n## PAYLOAD\n{payload}")
        
        return "\n".join(prompt_parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'system_prompt': self.system_prompt,
            'return_format': self.return_format,
            'return_format_type': self.return_format_type.value,
            'warnings': self.warnings,
            'payload_template': self.payload_template
        }


class PromptLibrary:
    """Library of reusable prompt templates for common operations."""
    
    def __init__(self):
        """Initialize the prompt library."""
        self.templates: Dict[str, PromptTemplate] = {}
        self._template_usage_count: Dict[str, int] = {}
        self._format_history: List[str] = []
        self._initialize_templates()
    
    def _initialize_templates(self):
        """Initialize default prompt templates."""
        
        # Extract entities from complaint
        self.register_template(PromptTemplate(
            name='extract_entities',
            system_prompt="""You are a legal assistant specialized in extracting structured information from complaint narratives.
Your task is to identify key entities such as parties involved, dates, locations, and other relevant facts.""",
            return_format="""Return a JSON object with the following structure:
{
  "entities": [
    {
      "text": "entity text",
      "type": "person|organization|location|date|amount|other",
      "role": "complainant|defendant|witness|other",
      "confidence": 0.0-1.0
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "Only extract entities explicitly mentioned in the text",
                "Do not infer or assume information not present",
                "Mark confidence < 0.8 if entity reference is ambiguous",
                "Include dates in ISO 8601 format when possible"
            ],
            payload_template="Extract entities from the following complaint text:\n\n{complaint_text}"
        ))
        
        # Extract relationships between entities
        self.register_template(PromptTemplate(
            name='extract_relationships',
            system_prompt="""You are a legal assistant specialized in identifying relationships between entities in legal complaints.
Your task is to extract how different entities are related to each other.""",
            return_format="""Return a JSON object with the following structure:
{
  "relationships": [
    {
      "source": "entity1",
      "target": "entity2",
      "type": "employed_by|owns|resides_at|manages|witnessed|other",
      "description": "brief description",
      "confidence": 0.0-1.0
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "Only extract relationships explicitly stated or strongly implied",
                "Mark confidence < 0.8 if relationship is unclear",
                "Use standard relationship types when possible"
            ],
            payload_template="Entities:\n{entities}\n\nComplaint text:\n{complaint_text}"
        ))
        
        # Generate denoising questions
        self.register_template(PromptTemplate(
            name='generate_questions',
            system_prompt="""You are a skilled mediator helping to gather complete information about a legal complaint.
Your task is to generate clarifying questions that will help fill gaps in the complaint narrative.""",
            return_format="""Return a JSON object with the following structure:
{
  "questions": [
    {
      "question": "clear, specific question",
      "field": "field_name_this_question_addresses",
      "priority": "high|medium|low",
      "reasoning": "why this question is important"
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "Questions should be clear, specific, and answerable",
                "Prioritize required information over optional details",
                "Avoid leading or biased questions",
                "Ask one thing per question"
            ],
            payload_template="Complaint type: {complaint_type}\n\nCurrent information:\n{current_info}\n\nMissing fields:\n{missing_fields}"
        ))
        
        # Extract legal claims
        self.register_template(PromptTemplate(
            name='extract_claims',
            system_prompt="""You are a legal analyst specialized in identifying potential legal claims from complaint narratives.
Your task is to identify what legal causes of action may be present.""",
            return_format="""Return a JSON object with the following structure:
{
  "claims": [
    {
      "claim_type": "discrimination|breach_of_contract|negligence|etc",
      "legal_basis": "statute or common law basis",
      "supporting_facts": ["fact1", "fact2"],
      "confidence": 0.0-1.0
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "Only identify claims with reasonable legal support",
                "Mark confidence < 0.7 if supporting facts are weak",
                "Cite specific statutes when applicable",
                "Do not provide legal advice, only identify potential claims"
            ],
            payload_template="Complaint text:\n{complaint_text}\n\nJurisdiction: {jurisdiction}"
        ))
        
        # Extract legal requirements
        self.register_template(PromptTemplate(
            name='extract_requirements',
            system_prompt="""You are a legal analyst specialized in identifying the requirements needed to establish legal claims.
Your task is to determine what must be proven for each claim to succeed.""",
            return_format="""Return a JSON object with the following structure:
{
  "requirements": [
    {
      "claim_type": "claim type",
      "element": "element to be proven",
      "description": "what must be shown",
      "evidence_needed": "type of evidence required",
      "satisfied": true|false|null
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "List all required elements for each claim",
                "Mark satisfied=null if insufficient information to determine",
                "Be specific about evidence requirements",
                "Consider jurisdiction-specific variations"
            ],
            payload_template="Claims:\n{claims}\n\nAvailable facts:\n{facts}\n\nJurisdiction: {jurisdiction}"
        ))
        
        # Synthesize summary
        self.register_template(PromptTemplate(
            name='synthesize_summary',
            system_prompt="""You are a legal assistant creating a human-readable summary of a complaint.
Your task is to synthesize information from multiple sources into a coherent narrative.""",
            return_format="""Return a structured text summary with the following sections:
- Parties Involved
- Nature of Complaint
- Key Facts
- Timeline of Events
- Available Evidence
- Legal Issues
- Completeness Assessment""",
            return_format_type=ReturnFormat.STRUCTURED_TEXT,
            warnings=[
                "Use clear, professional language",
                "Present facts objectively without bias",
                "Note any gaps or uncertainties",
                "Keep summary concise but comprehensive"
            ],
            payload_template="""Knowledge graph entities: {entities}
Relationships: {relationships}
Claims: {claims}
Evidence: {evidence}
Conversation excerpts: {conversation}"""
        ))
        
        # Evaluate evidence
        self.register_template(PromptTemplate(
            name='evaluate_evidence',
            system_prompt="""You are a legal analyst evaluating the quality and relevance of evidence for legal claims.
Your task is to assess how well evidence supports the alleged claims.""",
            return_format="""Return a JSON object with the following structure:
{
  "evidence_evaluations": [
    {
      "evidence_id": "id",
      "claim_supported": "claim type",
      "relevance": 0.0-1.0,
      "reliability": 0.0-1.0,
      "strength": "strong|moderate|weak",
      "gaps": ["gap1", "gap2"]
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "Consider admissibility issues",
                "Assess credibility of sources",
                "Identify corroboration or conflicts",
                "Note what additional evidence is needed"
            ],
            payload_template="Claims:\n{claims}\n\nEvidence:\n{evidence}"
        ))
        
        # Generate formal complaint
        self.register_template(PromptTemplate(
            name='generate_formal_complaint',
            system_prompt="""You are a legal document specialist creating formal legal complaints.
Your task is to draft a complaint according to the applicable rules of civil procedure.""",
            return_format="""Return a structured document with:
1. Caption (case title, court, case number)
2. Parties section
3. Jurisdiction and venue
4. Statement of facts (numbered paragraphs)
5. Causes of action (numbered counts)
6. Prayer for relief
7. Signature block""",
            return_format_type=ReturnFormat.STRUCTURED_TEXT,
            warnings=[
                "Follow rules of civil procedure for the jurisdiction",
                "Use clear, numbered paragraphs",
                "State facts concisely and chronologically",
                "Separate causes of action into distinct counts",
                "Be specific about relief sought"
            ],
            payload_template="""Jurisdiction: {jurisdiction}
Court: {court}
Parties: {parties}
Facts: {facts}
Claims: {claims}
Relief sought: {relief}"""
        ))
        
        # Assess legal viability
        self.register_template(PromptTemplate(
            name='assess_viability',
            system_prompt="""You are a legal analyst assessing the viability of legal claims.
Your task is to evaluate how likely each claim is to succeed based on available facts and evidence.""",
            return_format="""Return a JSON object with the following structure:
{
  "claim_assessments": [
    {
      "claim_type": "claim type",
      "viability": "strong|moderate|weak|insufficient",
      "confidence": 0.0-1.0,
      "strengths": ["strength1", "strength2"],
      "weaknesses": ["weakness1", "weakness2"],
      "fact_finding_needed": ["needed_fact1", "needed_fact2"]
    }
  ]
}""",
            return_format_type=ReturnFormat.JSON,
            warnings=[
                "Consider both legal and factual sufficiency",
                "Identify dispositive weaknesses",
                "Note statute of limitations concerns",
                "Consider affirmative defenses",
                "This is assessment only, not legal advice"
            ],
            payload_template="Claims: {claims}\n\nFacts: {facts}\n\nEvidence: {evidence}\n\nJurisdiction: {jurisdiction}"
        ))
    
    def register_template(self, template: PromptTemplate):
        """Register a new template."""
        self.templates[template.name] = template
        logger.debug(f"Registered prompt template: {template.name}")
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """Get a template by name."""
        return self.templates.get(name)
    
    def list_templates(self) -> List[str]:
        """List all registered template names."""
        return list(self.templates.keys())
    
    def format_prompt(self, template_name: str, payload_data: Dict[str, Any]) -> str:
        """
        Format a prompt using a registered template.
        
        Args:
            template_name: Name of template to use
            payload_data: Data to fill in the payload
            
        Returns:
            Formatted prompt string
        """
        template = self.get_template(template_name)
        if not template:
            raise KeyError(f"Template not found: {template_name}")
        
        # Track usage
        self._template_usage_count[template_name] = self._template_usage_count.get(template_name, 0) + 1
        self._format_history.append(template_name)
        
        return template.format(payload_data)

    # =====================================================================
    # Batch 216: Template library analysis methods
    # =====================================================================
    
    def total_templates(self) -> int:
        """Return the total number of registered templates."""
        return len(self.templates)
    
    def templates_by_format_type(self, format_type: ReturnFormat) -> int:
        """
        Return count of templates using a specific return format type.
        
        Args:
            format_type: The ReturnFormat to filter by
            
        Returns:
            Count of templates with that format type
        """
        return sum(1 for t in self.templates.values() 
                  if t.return_format_type == format_type)
    
    def format_type_distribution(self) -> Dict[str, int]:
        """
        Return frequency distribution of return format types.
        
        Returns:
            Dict mapping format type to count
        """
        dist = {}
        for template in self.templates.values():
            format_name = template.return_format_type.value
            dist[format_name] = dist.get(format_name, 0) + 1
        return dist
    
    def templates_with_warnings(self) -> int:
        """Return count of templates that have warnings defined."""
        return sum(1 for t in self.templates.values() if t.warnings)
    
    def average_warnings_per_template(self) -> float:
        """Return average number of warnings per template."""
        if not self.templates:
            return 0.0
        total_warnings = sum(len(t.warnings) for t in self.templates.values())
        return total_warnings / len(self.templates)
    
    def maximum_warnings_count(self) -> int:
        """Return the maximum number of warnings in any single template."""
        if not self.templates:
            return 0
        return max(len(t.warnings) for t in self.templates.values())
    
    def warning_coverage_percentage(self) -> float:
        """Return percentage of templates that have at least one warning."""
        if not self.templates:
            return 0.0
        return (self.templates_with_warnings() / len(self.templates)) * 100
    
    def most_common_format_type(self) -> Optional[str]:
        """Return the most frequently used return format type."""
        dist = self.format_type_distribution()
        if not dist:
            return None
        return max(dist.items(), key=lambda x: x[1])[0]
    
    def total_format_operations(self) -> int:
        """Return total number of times format_prompt has been called."""
        return len(self._format_history)
    
    def most_used_template(self) -> Optional[str]:
        """Return the name of the most frequently used template."""
        if not self._template_usage_count:
            return None
        return max(self._template_usage_count.items(), key=lambda x: x[1])[0]
    
    # =====================================================================
    # Batch 214: PromptLibrary Validation and Caching Methods
    # =====================================================================
    
    def template_usage_count(self, template_name: str) -> int:
        """
        Get the usage count for a specific template.
        
        Args:
            template_name: Name of template to check
            
        Returns:
            Number of times this template has been formatted
        """
        return self._template_usage_count.get(template_name, 0)
    
    def validate_template_fields(self, template_name: str, payload_data: Dict[str, Any]) -> list[str]:
        """
        Validate that payload data contains all required fields for a template.
        
        Args:
            template_name: Name of template to validate against
            payload_data: Data to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        template = self.get_template(template_name)
        if not template:
            return [f"Template not found: {template_name}"]
        
        errors = []
        
        # Check for required fields in payload_template
        # Simple heuristic: look for {field_name} patterns
        import re
        field_pattern = re.compile(r'\{(\w+)\}')
        required_fields = set(field_pattern.findall(template.payload_template))
        
        for field in required_fields:
            if field not in payload_data:
                errors.append(f"Missing required field '{field}' for template '{template_name}'")
            elif payload_data[field] is None or (isinstance(payload_data[field], str) and not payload_data[field].strip()):
                errors.append(f"Field '{field}' is empty for template '{template_name}'")
        
        return errors
    
    def get_template_metadata(self, template_name: str) -> Dict[str, Any]:
        """
        Get metadata about a template (usage, format type, warnings).
        
        Args:
            template_name: Name of template
            
        Returns:
            Dictionary with template metadata
        """
        template = self.get_template(template_name)
        if not template:
            return {}
        
        return {
            'name': template.name,
            'format_type': template.return_format_type.value,
            'usage_count': self.template_usage_count(template_name),
            'warning_count': len(template.warnings),
            'has_payload': bool(template.payload_template),
            'system_prompt_length': len(template.system_prompt),
            'return_format_length': len(template.return_format)
        }
    
    def templates_by_usage(self, top_n: Optional[int] = None) -> list[tuple[str, int]]:
        """
        Get templates sorted by usage count (most used first).
        
        Args:
            top_n: Optional limit on number of results
            
        Returns:
            List of (template_name, usage_count) tuples sorted by usage
        """
        items = sorted(self._template_usage_count.items(), key=lambda x: x[1], reverse=True)
        if top_n is None:
            return items
        return items[:top_n]
    
    def unused_templates(self) -> list[str]:
        """
        Get list of templates that have never been used.
        
        Returns:
            Names of templates with zero usage count
        """
        used_templates = set(self._template_usage_count.keys())
        all_templates = set(self.templates.keys())
        return sorted(list(all_templates - used_templates))
    
    def templates_needing_payload(self) -> list[str]:
        """
        Get templates that expect payload data (have placeholders).
        
        Returns:
            List of template names that require payload data
        """
        result = []
        import re
        field_pattern = re.compile(r'\{(\w+)\}')
        
        for name, template in self.templates.items():
            if field_pattern.search(template.payload_template):
                result.append(name)
        
        return sorted(result)
    
    def templates_without_payload(self) -> list[str]:
        """
        Get templates that don't require payload data.
        
        Returns:
            List of template names with no placeholders
        """
        all_names = set(self.templates.keys())
        with_payload = set(self.templates_needing_payload())
        return sorted(list(all_names - with_payload))
    
    def warning_distribution(self) -> Dict[int, int]:
        """
        Get distribution of warning counts across templates.
        
        Returns:
            Dict mapping warning count to number of templates with that count
        """
        dist = {}
        for template in self.templates.values():
            warning_count = len(template.warnings)
            dist[warning_count] = dist.get(warning_count, 0) + 1
        return dist
    
    def templates_with_most_warnings(self) -> Optional[str]:
        """
        Find the template that has the most warnings.
        
        Returns:
            Template name with most warnings, or None if no templates
        """
        if not self.templates:
            return None
        
        max_template = None
        max_count = 0
        
        for name, template in self.templates.items():
            warning_count = len(template.warnings)
            if warning_count > max_count:
                max_count = warning_count
                max_template = name
        
        return max_template
    
    def system_prompt_length_distribution(self) -> Dict[str, int]:
        """
        Get distribution of system prompt lengths.
        
        Returns:
            Dict with statistics about system prompt lengths
        """
        lengths = [len(t.system_prompt) for t in self.templates.values()]
        
        if not lengths:
            return {'total_templates': 0}
        
        return {
            'total_templates': len(lengths),
            'average_length': int(sum(lengths) / len(lengths)),
            'min_length': min(lengths),
            'max_length': max(lengths),
            'total_chars': sum(lengths)
        }
    
    def clear_usage_statistics(self) -> None:
        """Clear all usage tracking and history data."""
        self._template_usage_count.clear()
        self._format_history.clear()
    
    def get_usage_history(self, limit: Optional[int] = None) -> list[str]:
        """
        Get history of template usage.
        
        Args:
            limit: Optional limit on number of most recent entries
            
        Returns:
            List of template names in usage order
        """
        if limit is None:
            return list(self._format_history)
        if limit <= 0:
            return []
        return self._format_history[-limit:]
    
    def template_format_type_breakdown(self) -> Dict[str, list[str]]:
        """
        Get templates grouped by their return format type.
        
        Returns:
            Dict mapping format type names to lists of template names
        """
        breakdown = {}
        for name, template in self.templates.items():
            format_name = template.return_format_type.value
            if format_name not in breakdown:
                breakdown[format_name] = []
            breakdown[format_name].append(name)
        
        # Sort template lists
        for format_name in breakdown:
            breakdown[format_name].sort()
        
        return breakdown
    
    def total_characters_in_templates(self) -> int:
        """
        Calculate total characters across all template content.
        
        Returns:
            Sum of characters in all system prompts, return formats, and payloads
        """
        total = 0
        for template in self.templates.values():
            total += len(template.system_prompt)
            total += len(template.return_format)
            total += len(template.payload_template)
        return total
    
    def cache_efficiency_ratio(self) -> float:
        """
        Calculate ratio of successful cached template retrievals.
        
        Returns:
            Ratio (0.0 to 1.0) of format operations to unique template count
        """
        if not self.templates:
            return 0.0
        
        total_formats = len(self._format_history)
        if total_formats == 0:
            return 0.0
        
        # Efficiency: how many times we format vs how many unique templates we have
        # Higher ratio = more reuse of templates
        unique_templates_used = len(set(self._format_history))
        return unique_templates_used / max(1, total_formats)
