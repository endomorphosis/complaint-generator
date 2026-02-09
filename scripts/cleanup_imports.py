#!/usr/bin/env python3
"""
Script to clean up unused imports across the codebase based on PR review comments.
"""

import re
from pathlib import Path

# Map of files to unused imports
UNUSED_IMPORTS = {
    'adversarial_harness/complainant.py': [
        ('Optional', 'typing'),
        ('field', 'dataclasses'),
    ],
    'adversarial_harness/harness.py': [
        ('Optional', 'typing'),
    ],
    'adversarial_harness/optimizer.py': [
        ('Optional', 'typing'),
        ('field', 'dataclasses'),
        ('json', None),
    ],
    'adversarial_harness/session.py': [
        ('Optional', 'typing'),
        ('field', 'dataclasses'),
    ],
    'adversarial_harness/search_hooks.py': [
        ('json', None),
        ('Optional', 'typing'),
    ],
    'complaint_analysis/decision_trees.py': [
        ('get_keywords', '.keywords'),
        ('get_legal_terms', '.legal_patterns'),
    ],
    'complaint_analysis/prompt_templates.py': [
        ('json', None),
    ],
    'complaint_analysis/seed_generator.py': [
        ('get_keywords', '.keywords'),
    ],
    'complaint_phases/dependency_graph.py': [
        ('Set', 'typing'),
    ],
    'complaint_phases/knowledge_graph.py': [
        ('Set', 'typing'),
        ('Tuple', 'typing'),
    ],
    'complaint_phases/neurosymbolic_matcher.py': [
        ('Optional', 'typing'),
        ('Tuple', 'typing'),
    ],
    'complaint_phases/phase_manager.py': [
        ('Optional', 'typing'),
        ('List', 'typing'),
    ],
    'mediator/legal_corpus_hooks.py': [
        ('json', None),
        ('Set', 'typing'),
        ('Path', 'pathlib'),
        ('get_keywords', 'complaint_analysis.keywords'),
        ('get_registered_types', 'complaint_analysis.complaint_types'),
    ],
    'tests/test_search_hooks.py': [
        ('MagicMock', 'unittest.mock'),
        ('patch', 'unittest.mock'),
    ],
    'tests/test_adversarial_harness.py': [
        ('ComplaintGenerator', None),  # Multi-line import
    ],
    'tests/test_complaint_analysis_integration.py': [
        ('SeedComplaintTemplate', None),
        ('QuestionNode', None),
    ],
    'tests/test_complaint_phases.py': [
        ('pytest', None),
        ('json', None),
        ('tempfile', None),
        ('os', None),
    ],
    'tests/test_enhanced_denoising.py': [
        ('LegalGraphBuilder', None),
        ('NeurosymbolicMatcher', None),
    ],
    'tests/test_mediator_three_phase.py': [
        ('NodeType', None),
    ],
    'examples/complaint_analysis_integration_demo.py': [
        ('StateFileIngester', None),
    ],
    'examples/search_hooks_demo.py': [
        ('Path', 'pathlib'),
    ],
}

def remove_unused_import(filepath: Path, import_name: str, module: str = None):
    """Remove an unused import from a file."""
    content = filepath.read_text()
    original = content
    
    if module:
        # Handle specific imports like "from X import Y"
        patterns = [
            # Single import: from X import Y
            rf'from {re.escape(module)} import {re.escape(import_name)}\n',
            # Multiple imports, remove one: from X import A, B, C
            rf'from {re.escape(module)} import ([^,\n]+, )*{re.escape(import_name)}(, [^,\n]+)*\n',
            # Remove from multi-line list
            rf',\s*{re.escape(import_name)}\s*\n',
            rf'\s*{re.escape(import_name)},?\s*\n',
        ]
    else:
        # Handle simple imports like "import X"
        patterns = [
            rf'import {re.escape(import_name)}\n',
        ]
    
    for pattern in patterns:
        content = re.sub(pattern, '', content)
    
    # Clean up empty import lines
    content = re.sub(r'from ([^\s]+) import\s*\n', '', content)
    
    if content != original:
        filepath.write_text(content)
        return True
    return False

def main():
    repo_root = Path(__file__).parent.parent
    removed_count = 0
    
    for file_path, imports in UNUSED_IMPORTS.items():
        full_path = repo_root / file_path
        if not full_path.exists():
            print(f"❌ File not found: {file_path}")
            continue
        
        print(f"\n📝 Processing: {file_path}")
        for import_name, module in imports:
            if remove_unused_import(full_path, import_name, module):
                print(f"  ✅ Removed: {import_name} from {module or 'builtin'}")
                removed_count += 1
            else:
                print(f"  ⚠️  Could not remove: {import_name}")
    
    print(f"\n🎉 Removed {removed_count} unused imports")

if __name__ == '__main__':
    main()
