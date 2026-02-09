"""
Seed Complaints Library

Templates and generators for seed complaints across different types.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class ComplaintTemplate:
    """Template for generating seed complaints."""
    id: str
    type: str
    category: str
    description: str
    key_facts_template: Dict[str, Any]
    required_fields: List[str]
    optional_fields: List[str]
    
    def instantiate(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a concrete complaint from this template.
        
        Args:
            values: Values to fill in the template
            
        Returns:
            Instantiated complaint data
        """
        # Check required fields
        missing = [f for f in self.required_fields if f not in values]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
        # Merge template with values
        key_facts = self.key_facts_template.copy()
        key_facts.update(values)
        
        return {
            'template_id': self.id,
            'type': self.type,
            'category': self.category,
            'description': self.description,
            'key_facts': key_facts
        }


class SeedComplaintLibrary:
    """
    Library of seed complaints for testing.
    
    Provides templates and seed data for generating diverse test scenarios.
    """
    
    def __init__(self):
        """Initialize the seed complaint library."""
        self.templates = {}
        self._initialize_templates()
    
    def _initialize_templates(self):
        """Initialize default complaint templates."""
        
        # Employment discrimination template
        self.register_template(ComplaintTemplate(
            id='employment_discrimination_1',
            type='employment_discrimination',
            category='employment',
            description='Workplace discrimination based on protected class',
            key_facts_template={
                'employer': None,
                'position': None,
                'protected_class': None,
                'discriminatory_action': None,
                'date': None,
                'witnesses': []
            },
            required_fields=['employer', 'position', 'protected_class', 'discriminatory_action'],
            optional_fields=['date', 'witnesses', 'prior_complaints']
        ))
        
        # Housing discrimination template
        self.register_template(ComplaintTemplate(
            id='housing_discrimination_1',
            type='housing_discrimination',
            category='housing',
            description='Housing discrimination based on protected class',
            key_facts_template={
                'landlord': None,
                'property_address': None,
                'protected_class': None,
                'discriminatory_action': None,
                'date': None
            },
            required_fields=['landlord', 'protected_class', 'discriminatory_action'],
            optional_fields=['property_address', 'date', 'witnesses']
        ))
        
        # Wrongful termination template
        self.register_template(ComplaintTemplate(
            id='wrongful_termination_1',
            type='wrongful_termination',
            category='employment',
            description='Wrongful termination without cause',
            key_facts_template={
                'employer': None,
                'position': None,
                'termination_date': None,
                'termination_reason': None,
                'years_employed': None,
                'performance_record': None
            },
            required_fields=['employer', 'position', 'termination_date'],
            optional_fields=['termination_reason', 'years_employed', 'performance_record']
        ))
        
        # Consumer fraud template
        self.register_template(ComplaintTemplate(
            id='consumer_fraud_1',
            type='consumer_fraud',
            category='consumer',
            description='Fraudulent business practices',
            key_facts_template={
                'business': None,
                'product_service': None,
                'fraud_type': None,
                'amount_lost': None,
                'date': None
            },
            required_fields=['business', 'product_service', 'fraud_type'],
            optional_fields=['amount_lost', 'date', 'attempts_to_resolve']
        ))
    
    def register_template(self, template: ComplaintTemplate):
        """Register a new template."""
        self.templates[template.id] = template
        logger.debug(f"Registered template: {template.id}")
    
    def get_template(self, template_id: str) -> ComplaintTemplate:
        """Get a template by ID."""
        if template_id not in self.templates:
            raise KeyError(f"Template not found: {template_id}")
        return self.templates[template_id]
    
    def list_templates(self, category: str = None) -> List[ComplaintTemplate]:
        """
        List available templates.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of templates
        """
        templates = list(self.templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates
    
    def get_seed_complaints(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get a set of pre-defined seed complaints.
        
        Args:
            count: Number of seeds to return
            
        Returns:
            List of seed complaint data
        """
        seeds = []
        
        # Employment discrimination examples
        seeds.extend([
            {
                'template_id': 'employment_discrimination_1',
                'type': 'employment_discrimination',
                'category': 'employment',
                'key_facts': {
                    'employer': 'Acme Corporation',
                    'position': 'Senior Engineer',
                    'protected_class': 'race',
                    'discriminatory_action': 'passed over for promotion',
                    'date': '2024-01-15'
                },
                'summary': 'Passed over for promotion due to race'
            },
            {
                'template_id': 'employment_discrimination_1',
                'type': 'employment_discrimination',
                'category': 'employment',
                'key_facts': {
                    'employer': 'Tech Solutions Inc',
                    'position': 'Manager',
                    'protected_class': 'gender',
                    'discriminatory_action': 'pay disparity',
                    'date': '2024-02-01'
                },
                'summary': 'Paid less than male colleagues in same role'
            },
        ])
        
        # Housing discrimination examples
        seeds.extend([
            {
                'template_id': 'housing_discrimination_1',
                'type': 'housing_discrimination',
                'category': 'housing',
                'key_facts': {
                    'landlord': 'Property Management LLC',
                    'property_address': '123 Main St',
                    'protected_class': 'familial status',
                    'discriminatory_action': 'refused rental application',
                    'date': '2024-03-01'
                },
                'summary': 'Refused rental because I have children'
            },
        ])
        
        # Wrongful termination examples
        seeds.extend([
            {
                'template_id': 'wrongful_termination_1',
                'type': 'wrongful_termination',
                'category': 'employment',
                'key_facts': {
                    'employer': 'Global Industries',
                    'position': 'Sales Manager',
                    'termination_date': '2024-04-01',
                    'termination_reason': 'downsizing',
                    'years_employed': 8,
                    'performance_record': 'excellent'
                },
                'summary': 'Fired after whistleblowing on accounting fraud'
            },
        ])
        
        # Consumer fraud examples
        seeds.extend([
            {
                'template_id': 'consumer_fraud_1',
                'type': 'consumer_fraud',
                'category': 'consumer',
                'key_facts': {
                    'business': 'QuickFix Auto Repair',
                    'product_service': 'car repair',
                    'fraud_type': 'unnecessary repairs',
                    'amount_lost': 2500,
                    'date': '2024-05-01'
                },
                'summary': 'Charged for repairs that were never needed'
            },
        ])
        
        return seeds[:count]
    
    def create_seed_from_template(self, 
                                  template_id: str,
                                  values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a seed complaint from a template.
        
        Args:
            template_id: ID of template to use
            values: Values to fill in template
            
        Returns:
            Seed complaint data
        """
        template = self.get_template(template_id)
        return template.instantiate(values)
