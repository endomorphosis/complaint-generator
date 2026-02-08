"""
Complaint Type Registration

Provides convenience functions for registering different complaint types
with their specific keywords, patterns, and scoring models.
"""

from typing import List
from .keywords import register_keywords
from .legal_patterns import register_legal_terms


def register_housing_complaint():
    """Register keywords and patterns for housing complaints."""
    # Already registered in keywords.py, but this allows for programmatic registration
    pass


def register_employment_complaint():
    """Register keywords and patterns for employment complaints."""
    # Already registered in keywords.py
    pass


def register_civil_rights_complaint():
    """Register keywords and patterns for civil rights complaints."""
    # Additional civil rights specific keywords
    register_keywords('complaint', [
        'police brutality', 'excessive force',
        'unlawful search', 'unlawful seizure',
        'first amendment', 'freedom of speech',
        'freedom of assembly', 'voting rights',
    ], complaint_type='civil_rights')


def register_consumer_complaint():
    """Register keywords and patterns for consumer protection complaints."""
    register_keywords('complaint', [
        'fraud', 'deception', 'misrepresentation',
        'unfair practice', 'deceptive practice',
        'false advertising', 'bait and switch',
        'warranty breach', 'consumer protection',
        'ftc', 'federal trade commission',
    ], complaint_type='consumer')
    
    register_legal_terms('consumer', [
        r'\b(fraud|fraudulent)\b',
        r'\b(deceptive (practice|trade))\b',
        r'\b(false advertising)\b',
        r'\b(consumer protection)\b',
        r'\b(ftc|federal trade commission)\b',
    ])


def register_healthcare_complaint():
    """Register keywords and patterns for healthcare complaints."""
    register_keywords('complaint', [
        'medical malpractice', 'negligence',
        'hipaa', 'medical privacy',
        'patient rights', 'informed consent',
        'emergency medical', 'emtala',
    ], complaint_type='healthcare')


def register_free_speech_complaint():
    """Register keywords and patterns for censorship and free speech complaints."""
    register_keywords('complaint', [
        # First Amendment
        'first amendment', 'free speech', 'freedom of speech',
        'freedom of expression', 'freedom of the press',
        'prior restraint', 'viewpoint discrimination',
        'content-based restriction', 'content-neutral',
        
        # Censorship
        'censorship', 'censor', 'censored',
        'suppression', 'silenced', 'deplatformed',
        'banned', 'suspension', 'account termination',
        
        # Social media / platforms
        'content moderation', 'platform moderation',
        'community guidelines', 'terms of service violation',
        'shadowban', 'demonetized', 'demonetization',
        'algorithm bias', 'content suppression',
        
        # Public forum / government
        'public forum', 'limited public forum',
        'government censorship', 'state action',
        'chilling effect', 'prior restraint',
        
        # Academic / institutional
        'academic freedom', 'intellectual freedom',
        'library censorship', 'book ban',
        'curriculum restriction',
        
        # Whistleblower / retaliation
        'whistleblower', 'retaliation for speech',
        'protected speech', 'political speech',
    ], complaint_type='free_speech')
    
    register_legal_terms('free_speech', [
        r'\b(first amendment)\b',
        r'\b(free(dom of)? speech)\b',
        r'\b(free(dom of)? (expression|press))\b',
        r'\b(prior restraint)\b',
        r'\b(viewpoint discrimination)\b',
        r'\b(content[- ]based restriction)\b',
        r'\b(public forum)\b',
        r'\b(state action)\b',
        r'\b(chilling effect)\b',
        r'\b(censorship|censor(ed)?)\b',
    ])


def register_immigration_complaint():
    """Register keywords and patterns for immigration law complaints."""
    register_keywords('complaint', [
        # Immigration status
        'immigration', 'immigrant', 'undocumented',
        'visa', 'green card', 'permanent resident',
        'naturalization', 'citizenship',
        'asylum', 'refugee', 'asylee',
        'temporary protected status', 'tps',
        'daca', 'dreamer', 'deferred action',
        
        # Agencies and processes
        'uscis', 'ice', 'cbp', 'immigration and customs enforcement',
        'customs and border protection',
        'immigration court', 'eoir', 'deportation',
        'removal proceedings', 'detention',
        'immigration detention', 'bond hearing',
        
        # Employment immigration
        'h-1b', 'h-2a', 'h-2b', 'l-1', 'o-1',
        'employment-based visa', 'labor certification',
        'perm', 'prevailing wage',
        
        # Family immigration
        'family-based immigration', 'family petition',
        'i-130', 'marriage-based green card',
        'adjustment of status', 'consular processing',
        
        # Immigration violations
        'immigration fraud', 'unlawful presence',
        'visa overstay', 'bars to admission',
        'inadmissibility', 'removal order',
        
        # Rights and remedies
        'withholding of removal', 'cancellation of removal',
        'relief from removal', 'stay of removal',
        'travel document', 'advance parole',
        'employment authorization', 'work permit',
    ], complaint_type='immigration')
    
    register_legal_terms('immigration', [
        r'\b(immigration|immigrant)\b',
        r'\b(visa|green card)\b',
        r'\b(asylum|refugee|asylee)\b',
        r'\b(deportation|removal)\b',
        r'\b(uscis|ice|cbp|eoir)\b',
        r'\b(daca|dreamer)\b',
        r'\b(h-?1b|h-?2[ab]|l-?1|o-?1)\b',
        r'\b(adjustment of status)\b',
        r'\b(withholding of removal)\b',
        r'\b(cancellation of removal)\b',
    ])


def register_family_law_complaint():
    """Register keywords and patterns for family law complaints."""
    register_keywords('complaint', [
        # Divorce / dissolution
        'divorce', 'dissolution of marriage',
        'legal separation', 'annulment',
        'marital property', 'community property',
        'equitable distribution', 'property division',
        
        # Child custody
        'child custody', 'parenting time', 'visitation',
        'sole custody', 'joint custody', 'shared custody',
        'physical custody', 'legal custody',
        'custodial parent', 'non-custodial parent',
        'parenting plan', 'custody order',
        
        # Child support
        'child support', 'support obligation',
        'child support arrears', 'support enforcement',
        'support modification',
        
        # Spousal support
        'alimony', 'spousal support', 'maintenance',
        'temporary support', 'rehabilitative support',
        'permanent support',
        
        # Domestic violence
        'domestic violence', 'domestic abuse',
        'protective order', 'restraining order',
        'order of protection', 'no-contact order',
        
        # Adoption / guardianship
        'adoption', 'guardianship', 'foster care',
        'termination of parental rights',
        
        # Paternity
        'paternity', 'parentage', 'genetic testing',
    ], complaint_type='family_law')
    
    register_legal_terms('family_law', [
        r'\b(divorce|dissolution)\b',
        r'\b(child custody|parenting time)\b',
        r'\b(child support)\b',
        r'\b(alimony|spousal support)\b',
        r'\b(domestic (violence|abuse))\b',
        r'\b((protective|restraining) order)\b',
        r'\b(adoption|guardianship)\b',
        r'\b(paternity|parentage)\b',
    ])


def register_criminal_defense_complaint():
    """Register keywords and patterns for criminal defense complaints."""
    register_keywords('complaint', [
        # Constitutional rights
        'fourth amendment', 'unreasonable search',
        'illegal search', 'warrantless search',
        'fifth amendment', 'self-incrimination',
        'miranda rights', 'right to remain silent',
        'sixth amendment', 'right to counsel',
        'effective assistance of counsel',
        'speedy trial', 'jury trial',
        'eighth amendment', 'cruel and unusual punishment',
        'excessive bail', 'excessive fine',
        
        # Due process
        'due process', 'procedural due process',
        'substantive due process', 'fundamental fairness',
        
        # Criminal procedure
        'arrest', 'detention', 'probable cause',
        'search warrant', 'arrest warrant',
        'suppression of evidence', 'exclusionary rule',
        'fruit of the poisonous tree',
        'interrogation', 'confession', 'coerced confession',
        
        # Criminal charges
        'criminal charge', 'indictment', 'information',
        'misdemeanor', 'felony', 'infraction',
        
        # Trial rights
        'jury selection', 'voir dire', 'peremptory challenge',
        'confrontation clause', 'cross-examination',
        'prosecutorial misconduct', 'brady violation',
        'exculpatory evidence',
        
        # Sentencing
        'sentencing', 'sentence enhancement',
        'three strikes', 'mandatory minimum',
        'parole', 'probation', 'supervised release',
        
        # Post-conviction
        'habeas corpus', 'post-conviction relief',
        'ineffective assistance', 'actual innocence',
        'wrongful conviction',
    ], complaint_type='criminal_defense')
    
    register_legal_terms('criminal_defense', [
        r'\b((fourth|fifth|sixth|eighth) amendment)\b',
        r'\b(miranda (rights|warning))\b',
        r'\b(right to (counsel|remain silent|jury trial))\b',
        r'\b(due process)\b',
        r'\b(unreasonable search)\b',
        r'\b(probable cause)\b',
        r'\b(exclusionary rule)\b',
        r'\b(brady violation)\b',
        r'\b(habeas corpus)\b',
        r'\b(ineffective assistance)\b',
    ])


def register_tax_law_complaint():
    """Register keywords and patterns for tax law complaints."""
    register_keywords('complaint', [
        # Tax agencies
        'irs', 'internal revenue service',
        'tax court', 'u.s. tax court',
        'state tax', 'state department of revenue',
        
        # Tax types
        'income tax', 'corporate tax', 'estate tax',
        'gift tax', 'payroll tax', 'employment tax',
        'excise tax', 'sales tax', 'property tax',
        
        # Tax processes
        'tax audit', 'examination', 'revenue agent',
        'notice of deficiency', 'statutory notice',
        'tax assessment', 'tax liability',
        'collection due process', 'cdp hearing',
        
        # Tax penalties
        'tax penalty', 'accuracy penalty',
        'fraud penalty', 'failure to file',
        'failure to pay', 'estimated tax penalty',
        
        # Tax remedies
        'innocent spouse relief', 'offer in compromise',
        'installment agreement', 'currently not collectible',
        'penalty abatement', 'interest abatement',
        
        # Tax collection
        'tax levy', 'tax lien', 'wage garnishment',
        'bank levy', 'seizure', 'collection action',
        
        # Tax procedure
        'tax return', 'amended return', 'refund claim',
        'statute of limitations', 'collection statute',
        'assessment statute',
    ], complaint_type='tax_law')
    
    register_legal_terms('tax_law', [
        r'\b(irs|internal revenue service)\b',
        r'\b(tax court)\b',
        r'\b(tax (audit|assessment|liability))\b',
        r'\b(notice of deficiency)\b',
        r'\b(tax (penalty|levy|lien))\b',
        r'\b(innocent spouse)\b',
        r'\b(offer in compromise)\b',
        r'\b(collection due process)\b',
    ])


def register_intellectual_property_complaint():
    """Register keywords and patterns for intellectual property complaints."""
    register_keywords('complaint', [
        # Patents
        'patent', 'patent infringement',
        'utility patent', 'design patent',
        'patent pending', 'prior art',
        'obviousness', 'enablement',
        'patent claim', 'patent prosecution',
        
        # Trademarks
        'trademark', 'service mark', 'trade name',
        'trademark infringement', 'likelihood of confusion',
        'trademark dilution', 'famous mark',
        'generic mark', 'descriptive mark',
        'suggestive mark', 'arbitrary mark',
        'trade dress', 'secondary meaning',
        
        # Copyrights
        'copyright', 'copyright infringement',
        'fair use', 'transformative use',
        'derivative work', 'copyright registration',
        'dmca', 'digital millennium copyright act',
        'takedown notice', 'counter-notice',
        
        # Trade secrets
        'trade secret', 'confidential information',
        'misappropriation', 'utsa',
        'non-disclosure agreement', 'nda',
        'non-compete agreement',
        
        # General IP
        'intellectual property', 'ip', 'licensing',
        'royalty', 'license agreement',
        'infringement', 'cease and desist',
        'damages', 'injunctive relief',
    ], complaint_type='intellectual_property')
    
    register_legal_terms('intellectual_property', [
        r'\b(patent( infringement)?)\b',
        r'\b(trademark( infringement)?)\b',
        r'\b(copyright( infringement)?)\b',
        r'\b(trade secret)\b',
        r'\b(fair use)\b',
        r'\b(dmca)\b',
        r'\b(likelihood of confusion)\b',
        r'\b(trade dress)\b',
    ])


def register_environmental_law_complaint():
    """Register keywords and patterns for environmental law complaints."""
    register_keywords('complaint', [
        # Environmental agencies
        'epa', 'environmental protection agency',
        'clean air act', 'clean water act',
        'safe drinking water act',
        
        # Environmental issues
        'pollution', 'contamination',
        'air pollution', 'water pollution',
        'soil contamination', 'groundwater contamination',
        'toxic waste', 'hazardous waste',
        'hazardous substance', 'pollutant',
        
        # Environmental laws
        'cercla', 'superfund', 'rcra',
        'resource conservation and recovery act',
        'comprehensive environmental response',
        'nepa', 'environmental impact statement',
        'endangered species act', 'esa',
        
        # Environmental violations
        'environmental violation', 'permit violation',
        'discharge violation', 'emission violation',
        'npdes', 'national pollutant discharge',
        
        # Environmental liability
        'environmental liability', 'cleanup cost',
        'remediation', 'natural resource damage',
        'citizen suit', 'environmental enforcement',
        
        # Climate
        'greenhouse gas', 'carbon emission',
        'climate change', 'global warming',
    ], complaint_type='environmental_law')
    
    register_legal_terms('environmental_law', [
        r'\b(epa|environmental protection agency)\b',
        r'\b(clean (air|water) act)\b',
        r'\b(cercla|superfund)\b',
        r'\b(rcra)\b',
        r'\b(nepa)\b',
        r'\b(endangered species act)\b',
        r'\b((air|water) pollution)\b',
        r'\b((toxic|hazardous) waste)\b',
        r'\b(contamination|remediation)\b',
    ])


def get_registered_types() -> List[str]:
    """
    Get all registered complaint types.
    
    Returns:
        List of complaint type names
    """
    from .keywords import _global_registry
    return _global_registry.get_complaint_types()


# Register default types on module import
register_housing_complaint()
register_employment_complaint()
register_civil_rights_complaint()
register_consumer_complaint()
register_healthcare_complaint()
register_free_speech_complaint()
register_immigration_complaint()
register_family_law_complaint()
register_criminal_defense_complaint()
register_tax_law_complaint()
register_intellectual_property_complaint()
register_environmental_law_complaint()
