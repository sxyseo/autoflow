#!/usr/bin/env python3
"""
Quick validation script for test_skill_templates.py

This script validates that the test file is properly structured
and all imports work correctly, even without pytest installed.
"""

import sys
import ast
import inspect
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_test_file():
    """Validate the test file structure and imports."""
    print("Validating test_skill_templates.py...")
    print("=" * 60)

    test_file = Path(__file__).parent / "test_skill_templates.py"

    # 1. Check file exists
    if not test_file.exists():
        print("✗ Test file does not exist")
        return False
    print("✓ Test file exists")

    # 2. Parse as AST to check syntax
    try:
        with open(test_file, 'r') as f:
            source = f.read()
        tree = ast.parse(source)
        print("✓ Python syntax is valid")
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        return False

    # 3. Count test classes and methods
    test_classes = []
    test_methods = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name.startswith('Test'):
                test_classes.append(node.name)
                # Count test methods in this class
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                        test_methods.append(f"{node.name}.{item.name}")

    print(f"✓ Found {len(test_classes)} test classes")
    print(f"✓ Found {len(test_methods)} test methods")

    # 4. Check imports
    imports_found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == 'autoflow.skills.templates':
                for alias in node.names:
                    imports_found.append(alias.name)

    expected_imports = [
        'BUILTIN_TEMPLATES',
        'RenderedTemplate',
        'SkillTemplate',
        'TemplateCategory',
        'TemplateLoader',
        'TemplateLoaderError',
        'TemplateRenderer',
        'create_loader',
        'create_renderer',
    ]

    missing_imports = set(expected_imports) - set(imports_found)
    if missing_imports:
        print(f"✗ Missing imports: {missing_imports}")
        return False
    print(f"✓ All required imports present")

    # 5. Try to import the module
    try:
        # Import the templates module first
        from autoflow.skills import templates
        print("✓ autoflow.skills.templates module imports successfully")

        # Check that all expected classes exist
        assert hasattr(templates, 'SkillTemplate')
        assert hasattr(templates, 'TemplateRenderer')
        assert hasattr(templates, 'TemplateLoader')
        assert hasattr(templates, 'TemplateCategory')
        assert hasattr(templates, 'RenderedTemplate')
        assert hasattr(templates, 'TemplateLoaderError')
        assert hasattr(templates, 'BUILTIN_TEMPLATES')
        assert hasattr(templates, 'create_loader')
        assert hasattr(templates, 'create_renderer')
        print("✓ All required classes/functions exist in templates module")

    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except AssertionError as e:
        print(f"✗ Missing expected class/function: {e}")
        return False

    print("=" * 60)
    print("✅ All validation checks passed!")
    print()
    print(f"Test file: {test_file}")
    print(f"Test classes: {len(test_classes)}")
    print(f"Test methods: {len(test_methods)}")
    print()
    print("Note: To run these tests, use:")
    print("  pytest tests/test_skill_templates.py -v")

    return True


if __name__ == "__main__":
    success = validate_test_file()
    sys.exit(0 if success else 1)
