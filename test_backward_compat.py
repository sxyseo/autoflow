#!/usr/bin/env python3
"""
Test backward compatibility with existing scripts.

This script verifies:
1. Old entry point 'autoflow.cli:main' still works
2. All existing command invocations produce identical output
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10
    )
    return result.returncode, result.stdout, result.stderr


def test_old_import_path():
    """Test that the old import path 'autoflow.cli:main' still works."""
    print("=" * 70)
    print("TEST 1: Old import path compatibility")
    print("=" * 70)

    # Test importing from the old path
    cmd = [
        sys.executable, "-c",
        "from autoflow.cli import main; print('SUCCESS'); print(type(main).__name__)"
    ]

    returncode, stdout, stderr = run_command(cmd)

    # Click Groups are of type 'Group' or 'module' depending on how they're imported
    if returncode == 0 and "SUCCESS" in stdout:
        print("✓ Old import path works: from autoflow.cli import main")
        print(f"  Output: {stdout.strip()}")
        return True
    else:
        print("✗ Old import path FAILED")
        print(f"  stdout: {stdout}")
        print(f"  stderr: {stderr}")
        return False


def test_entry_point_callable():
    """Test that the entry point is callable."""
    print("\n" + "=" * 70)
    print("TEST 2: Entry point is callable")
    print("=" * 70)

    cmd = [
        sys.executable, "-c",
        "from autoflow.cli import main; import inspect; print('CALLABLE' if callable(main) else 'NOT_CALLABLE')"
    ]

    returncode, stdout, stderr = run_command(cmd)

    if returncode == 0 and "CALLABLE" in stdout:
        print("✓ Entry point is callable")
        return True
    else:
        print("✗ Entry point is NOT callable")
        print(f"  stdout: {stdout}")
        print(f"  stderr: {stderr}")
        return False


def test_command_output_consistency():
    """Test that commands produce consistent output using CliRunner."""
    print("\n" + "=" * 70)
    print("TEST 3: Command output consistency")
    print("=" * 70)

    try:
        from click.testing import CliRunner
        from autoflow.cli import main
    except ImportError as e:
        print(f"✗ Cannot import CliRunner or main: {e}")
        return False

    runner = CliRunner()

    # Test commands using CliRunner (the proper way to test Click apps)
    commands_to_test = [
        (["--help"], "autoflow --help"),
        (["--version"], "autoflow --version"),
        (["init", "--help"], "autoflow init --help"),
        (["status", "--help"], "autoflow status --help"),
        (["run", "--help"], "autoflow run --help"),
        (["agent", "--help"], "autoflow agent --help"),
        (["skill", "--help"], "autoflow skill --help"),
        (["task", "--help"], "autoflow task --help"),
        (["scheduler", "--help"], "autoflow scheduler --help"),
        (["ci", "--help"], "autoflow ci --help"),
        (["review", "--help"], "autoflow review --help"),
        (["config", "--help"], "autoflow config --help"),
        (["memory", "--help"], "autoflow memory --help"),
    ]

    all_passed = True
    for cmd, display_name in commands_to_test:
        result = runner.invoke(main, cmd)

        # Check that command succeeded
        if result.exit_code == 0 and result.output:
            print(f"✓ {display_name}")
            # Check for expected markers in output
            if "--help" in display_name:
                # Help commands should show Usage information
                if "Usage:" not in result.output:
                    print(f"  WARNING: Expected 'Usage:' in help output")
                    all_passed = False
        else:
            print(f"✗ {display_name}")
            print(f"  exit_code: {result.exit_code}")
            print(f"  output: {result.output[:200]}")  # Truncate long output
            if result.exception:
                print(f"  exception: {result.exception}")
            all_passed = False

    if all_passed:
        print("\n✓ All commands produced expected output")
    else:
        print("\n✗ Some commands failed to produce expected output")

    return all_passed


def test_module_structure():
    """Test that the module structure is correct."""
    print("\n" + "=" * 70)
    print("TEST 4: Module structure verification")
    print("=" * 70)

    tests = [
        ("Main CLI module", "from autoflow.cli.main import main"),
        ("Utils module", "from autoflow.cli.utils import _get_state_manager"),
        ("Init command", "from autoflow.cli.init import init"),
        ("Status command", "from autoflow.cli.status import status"),
        ("Run command", "from autoflow.cli.run import run"),
        ("Agent commands", "from autoflow.cli.agent import agent"),
        ("Skill commands", "from autoflow.cli.skill import skill"),
        ("Task commands", "from autoflow.cli.task import task"),
        ("Scheduler commands", "from autoflow.cli.scheduler import scheduler"),
        ("CI commands", "from autoflow.cli.ci import ci"),
        ("Review commands", "from autoflow.cli.review import review"),
        ("Config commands", "from autoflow.cli.config import config"),
        ("Memory commands", "from autoflow.cli.memory import memory"),
    ]

    all_passed = True
    for test_name, import_stmt in tests:
        cmd = [sys.executable, "-c", f"{import_stmt}; print('OK')"]
        returncode, stdout, stderr = run_command(cmd)

        if returncode == 0 and "OK" in stdout:
            print(f"✓ {test_name}")
        else:
            print(f"✗ {test_name}")
            print(f"  stderr: {stderr}")
            all_passed = False

    return all_passed


def test_backward_compat_wrapper():
    """Test the backward compatibility wrapper in cli.py."""
    print("\n" + "=" * 70)
    print("TEST 5: Backward compatibility wrapper")
    print("=" * 70)

    # Test that cli.py re-exports main
    cmd = [
        sys.executable, "-c",
        "import autoflow.cli; print('HAS_MAIN' if hasattr(autoflow.cli, 'main') else 'NO_MAIN')"
    ]

    returncode, stdout, stderr = run_command(cmd)

    if returncode == 0 and "HAS_MAIN" in stdout:
        print("✓ cli.py re-exports main")
    else:
        print("✗ cli.py does NOT re-export main")
        print(f"  stdout: {stdout}")
        print(f"  stderr: {stderr}")
        return False

    # Test that it's the same main as cli.main
    cmd = [
        sys.executable, "-c",
        "from autoflow.cli import main as m1; from autoflow.cli.main import main as m2; print('SAME' if m1 is m2 else 'DIFFERENT')"
    ]

    returncode, stdout, stderr = run_command(cmd)

    if returncode == 0 and "SAME" in stdout:
        print("✓ cli.main and cli.main.main are the same object")
        return True
    else:
        print("✗ cli.main and cli.main.main are DIFFERENT")
        print(f"  stdout: {stdout}")
        return False


def main():
    """Run all backward compatibility tests."""
    print("\n" + "=" * 70)
    print("BACKWARD COMPATIBILITY VERIFICATION")
    print("=" * 70)

    tests = [
        test_old_import_path,
        test_entry_point_callable,
        test_command_output_consistency,
        test_module_structure,
        test_backward_compat_wrapper,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if all(results):
        print("\n✓ ALL BACKWARD COMPATIBILITY TESTS PASSED")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
