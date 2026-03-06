#!/usr/bin/env python3
"""
Test Runner CLI for Autoflow.

A command-line tool for discovering, running, and analyzing tests.

Usage:
    python3 scripts/test_runner.py discover
    python3 scripts/test_runner.py run [--auto-retry] [--max-attempts N]
    python3 scripts/test_runner.py coverage [--threshold N]
    python3 scripts/test_runner.py detect-flaky [--runs N] [--quarantine]
    python3 scripts/test_runner.py quarantine list
    python3 scripts/test_runner.py quarantine remove <test_name>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from test_framework import (
    TestConfig,
    TestDiscovery,
    TestExecutor,
    FlakyTestDetector,
    TestFile,
)


# Path to flaky tests configuration
FLAKY_TESTS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "flaky_tests.json"


def load_quarantine_config() -> dict:
    """Load the flaky tests quarantine configuration.

    Returns:
        Dictionary containing quarantined tests and metadata.
    """
    if not FLAKY_TESTS_CONFIG_PATH.exists():
        return {
            "quarantined_tests": {},
            "metadata": {
                "description": "Flaky tests that have been quarantined.",
                "created_at": None,
                "last_updated": None
            }
        }

    with open(FLAKY_TESTS_CONFIG_PATH, "r") as f:
        return json.load(f)


def save_quarantine_config(config: dict) -> None:
    """Save the flaky tests quarantine configuration.

    Args:
        config: Dictionary containing quarantined tests and metadata.
    """
    FLAKY_TESTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Update timestamp
    config["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    if config["metadata"]["created_at"] is None:
        config["metadata"]["created_at"] = config["metadata"]["last_updated"]

    with open(FLAKY_TESTS_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def add_to_quarantine(test_name: str, pass_rate: float, runs: int, passed: int) -> None:
    """Add a test to the quarantine.

    Args:
        test_name: Full test name (e.g., "tests/test_file.py::test_function").
        pass_rate: Pass rate of the test (0.0 to 1.0).
        runs: Number of runs performed.
        passed: Number of passed runs.
    """
    config = load_quarantine_config()

    config["quarantined_tests"][test_name] = {
        "pass_rate": pass_rate,
        "runs": runs,
        "passed": passed,
        "failed": runs - passed,
        "quarantined_at": datetime.now(timezone.utc).isoformat()
    }

    save_quarantine_config(config)


def remove_from_quarantine(test_name: str) -> bool:
    """Remove a test from the quarantine.

    Args:
        test_name: Full test name to remove.

    Returns:
        True if the test was removed, False if it wasn't in quarantine.
    """
    config = load_quarantine_config()

    if test_name in config["quarantined_tests"]:
        del config["quarantined_tests"][test_name]
        save_quarantine_config(config)
        return True

    return False


def get_quarantined_tests() -> dict[str, dict]:
    """Get all quarantined tests.

    Returns:
        Dictionary of test names to their quarantine info.
    """
    config = load_quarantine_config()
    return config.get("quarantined_tests", {})


def cmd_discover(args: argparse.Namespace) -> int:
    """Discover and list all test files.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success).
    """
    config = TestConfig()
    discovery = TestDiscovery(config)
    test_files = discovery.discover()

    if not test_files:
        print("No test files found.")
        return 0

    total_tests = sum(len(f.test_functions) for f in test_files)

    print(f"Discovered {len(test_files)} test files ({total_tests} test functions):\n")

    for test_file in sorted(test_files, key=lambda f: str(f.path)):
        relative_path = test_file.path.relative_to(Path.cwd())
        print(f"  {relative_path}")
        if test_file.test_functions:
            for func in test_file.test_functions[:5]:  # Show first 5
                print(f"    - {func}")
            if len(test_file.test_functions) > 5:
                print(f"    ... and {len(test_file.test_functions) - 5} more")

    print(f"\ntest files found")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run tests with optional auto-retry.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    config = TestConfig()
    executor = TestExecutor(config)

    test_paths = args.tests if args.tests else None
    auto_retry = args.auto_retry
    max_attempts = args.max_attempts

    print(f"Running tests...")
    if auto_retry:
        print(f"  Auto-retry enabled (max attempts: {max_attempts})")

    result = executor.run_tests(
        test_paths=test_paths,
        auto_retry=auto_retry,
        max_attempts=max_attempts,
        verbose=True
    )

    print(f"\n{'='*60}")
    print(f"Test Results:")
    print(f"  Total:   {result.total}")
    print(f"  Passed:  {result.passed}")
    print(f"  Failed:  {result.failed}")
    print(f"  Skipped: {result.skipped}")
    print(f"  Errors:  {result.errors}")
    print(f"  Duration: {result.duration:.2f}s")
    print(f"{'='*60}")

    if result.success:
        print("\nAll tests passed!")
        return 0
    else:
        print(f"\nTests failed: {result.failed + result.errors}")
        return 1


def cmd_coverage(args: argparse.Namespace) -> int:
    """Run tests with coverage tracking.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    config = TestConfig()
    executor = TestExecutor(config)

    threshold = args.threshold if args.threshold else config.coverage_threshold

    print(f"Running tests with coverage (threshold: {threshold}%)...\n")

    success, coverage, output = executor.run_coverage(threshold=threshold)

    print(output)

    print(f"\n{'='*60}")
    print(f"Coverage Report:")
    print(f"  Coverage: {coverage:.1f}%")
    print(f"  Threshold: {threshold}%")
    print(f"  Status: {'PASSED' if success else 'FAILED'}")
    print(f"{'='*60}")

    if success:
        print(f"\nCoverage threshold met ({coverage:.1f}% >= {threshold}%)")
        return 0
    else:
        print(f"\nCoverage below threshold ({coverage:.1f}% < {threshold}%)")
        return 1


def cmd_detect_flaky(args: argparse.Namespace) -> int:
    """Detect flaky tests by running them multiple times.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success).
    """
    config = TestConfig()
    detector = FlakyTestDetector(config)

    runs = args.runs if args.runs else config.flaky_min_runs
    test_path = args.test if args.test else None
    quarantine = args.quarantine if hasattr(args, "quarantine") else False

    print(f"Detecting flaky tests ({runs} runs)...\n")

    flaky_tests = detector.detect(test_path=test_path, runs=runs)

    if not flaky_tests:
        print("No flaky tests detected.")
        return 0

    print(f"Found {len(flaky_tests)} flaky tests:\n")

    quarantined_count = 0
    for test_name, info in sorted(flaky_tests.items(), key=lambda x: -x[1]["pass_rate"]):
        print(f"  {test_name}")
        print(f"    Pass rate: {info['pass_rate']*100:.1f}% ({info['passed']}/{info['runs']})")
        print(f"    Quarantine recommended: {'Yes' if info['is_flaky'] else 'No'}")

        # Auto-quarantine if flag is set and test is flaky
        if quarantine and info["is_flaky"]:
            add_to_quarantine(
                test_name=test_name,
                pass_rate=info["pass_rate"],
                runs=info["runs"],
                passed=info["passed"]
            )
            print(f"    Status: QUARANTINED")
            quarantined_count += 1

        print()

    if quarantine and quarantined_count > 0:
        print(f"\n{quarantined_count} test(s) have been quarantined.")
        print(f"Run 'python3 scripts/test_runner.py quarantine list' to view all quarantined tests.")

    return 0


def cmd_quarantine_list(args: argparse.Namespace) -> int:
    """List all quarantined tests.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success).
    """
    quarantined = get_quarantined_tests()

    if not quarantined:
        print("No tests are currently quarantined.")
        return 0

    print(f"Quarantined tests ({len(quarantined)}):\n")

    for test_name, info in sorted(quarantined.items()):
        print(f"  {test_name}")
        print(f"    Pass rate: {info['pass_rate']*100:.1f}% ({info['passed']}/{info['runs']} passed)")
        print(f"    Quarantined at: {info.get('quarantined_at', 'unknown')}")
        print()

    return 0


def cmd_quarantine_remove(args: argparse.Namespace) -> int:
    """Remove a test from quarantine.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, 1 if test not found).
    """
    test_name = args.test_name

    if remove_from_quarantine(test_name):
        print(f"Removed '{test_name}' from quarantine.")
        return 0
    else:
        print(f"Test '{test_name}' is not in quarantine.")
        return 1


def cmd_quarantine_clear(args: argparse.Namespace) -> int:
    """Clear all tests from quarantine.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success).
    """
    config = load_quarantine_config()
    count = len(config.get("quarantined_tests", {}))

    if count == 0:
        print("No tests are currently quarantined.")
        return 0

    config["quarantined_tests"] = {}
    save_quarantine_config(config)

    print(f"Cleared {count} test(s) from quarantine.")
    return 0


def main() -> int:
    """Main entry point for the test runner CLI.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(
        description="Test Runner CLI for Autoflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/test_runner.py discover
    python3 scripts/test_runner.py run --auto-retry --max-attempts 3
    python3 scripts/test_runner.py coverage --threshold 80
    python3 scripts/test_runner.py detect-flaky --runs 10
    python3 scripts/test_runner.py detect-flaky --runs 5 --quarantine
    python3 scripts/test_runner.py quarantine list
    python3 scripts/test_runner.py quarantine remove "tests/test_file.py::test_name"
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Discover command
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover and list all test files"
    )

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run tests with optional auto-retry"
    )
    run_parser.add_argument(
        "--auto-retry",
        action="store_true",
        help="Enable auto-retry for failed tests"
    )
    run_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum retry attempts (default: 3)"
    )
    run_parser.add_argument(
        "tests",
        nargs="*",
        help="Specific test paths to run"
    )

    # Coverage command
    coverage_parser = subparsers.add_parser(
        "coverage",
        help="Run tests with coverage tracking"
    )
    coverage_parser.add_argument(
        "--threshold",
        type=int,
        help="Coverage threshold percentage (default: 80)"
    )

    # Detect-flaky command
    flaky_parser = subparsers.add_parser(
        "detect-flaky",
        help="Detect flaky tests"
    )
    flaky_parser.add_argument(
        "--runs",
        type=int,
        help="Number of runs to detect flaky tests (default: 3)"
    )
    flaky_parser.add_argument(
        "--test",
        type=str,
        help="Specific test path to check"
    )
    flaky_parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Automatically quarantine detected flaky tests"
    )

    # Quarantine command (with subcommands)
    quarantine_parser = subparsers.add_parser(
        "quarantine",
        help="Manage quarantined flaky tests"
    )
    quarantine_subparsers = quarantine_parser.add_subparsers(
        dest="quarantine_command",
        help="Quarantine action"
    )

    # Quarantine list
    quarantine_list_parser = quarantine_subparsers.add_parser(
        "list",
        help="List all quarantined tests"
    )

    # Quarantine remove
    quarantine_remove_parser = quarantine_subparsers.add_parser(
        "remove",
        help="Remove a test from quarantine"
    )
    quarantine_remove_parser.add_argument(
        "test_name",
        help="Full test name to remove from quarantine"
    )

    # Quarantine clear
    quarantine_clear_parser = quarantine_subparsers.add_parser(
        "clear",
        help="Clear all tests from quarantine"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Handle quarantine subcommands
    if args.command == "quarantine":
        if args.quarantine_command is None:
            quarantine_parser.print_help()
            return 0

        quarantine_handlers = {
            "list": cmd_quarantine_list,
            "remove": cmd_quarantine_remove,
            "clear": cmd_quarantine_clear,
        }

        handler = quarantine_handlers.get(args.quarantine_command)
        if handler:
            return handler(args)

        quarantine_parser.print_help()
        return 0

    # Route to appropriate command handler
    commands = {
        "discover": cmd_discover,
        "run": cmd_run,
        "coverage": cmd_coverage,
        "detect-flaky": cmd_detect_flaky,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
