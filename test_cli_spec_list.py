#!/usr/bin/env python3
"""Test script to verify CLI task list command."""

from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner

# Add the project root to the path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Use proper imports
from autoflow.cli import main


def test_cli_task_list():
    """Test CLI task list command."""
    print("Testing CLI task list command...")
    runner = CliRunner()

    # Test task list
    result = runner.invoke(main, ['task', 'list'])

    print(f"Exit code: {result.exit_code}")
    print(f"Output:\n{result.output}")

    if result.exit_code == 0:
        if 'task-test-001' in result.output:
            print("\n✓ task-test-001 appears in CLI output")
            return True
        else:
            print("\n✗ task-test-001 does NOT appear in CLI output")
            return False
    else:
        print(f"\n✗ Command failed with exit code {result.exit_code}")
        if result.exception:
            print(f"Exception: {result.exception}")
        return False


if __name__ == "__main__":
    try:
        success = test_cli_task_list()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
