#!/usr/bin/env python3
"""Test script to verify CLI spec list command."""

import sys
from pathlib import Path
import importlib.util

# Load CLI module directly without going through __init__.py
spec = importlib.util.spec_from_file_location("cli", "autoflow/cli.py")
cli_module = importlib.util.module_from_spec(spec)

# Set up necessary modules in sys.modules
sys.modules['autoflow.cli'] = cli_module

# Mock the imports that fail
import sys
from unittest.mock import MagicMock

# Mock the problematic imports
sys.modules['autoflow.core.orchestrator'] = MagicMock()
sys.modules['autoflow.core'] = MagicMock()

# Now load the cli module
spec.loader.exec_module(cli_module)

def test_cli_spec_list():
    """Test CLI spec list command."""
    from click.testing import CliRunner

    print("Testing CLI spec list command...")
    runner = CliRunner()

    # Test spec list
    result = runner.invoke(cli_module.main, ['spec', 'list'])

    print(f"Exit code: {result.exit_code}")
    print(f"Output:\n{result.output}")

    if result.exit_code == 0:
        if 'test-spec' in result.output:
            print("\n✓ test-spec appears in CLI output")
            return True
        else:
            print("\n✗ test-spec does NOT appear in CLI output")
            return False
    else:
        print(f"\n✗ Command failed with exit code {result.exit_code}")
        if result.exception:
            print(f"Exception: {result.exception}")
        return False

if __name__ == "__main__":
    try:
        success = test_cli_spec_list()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
