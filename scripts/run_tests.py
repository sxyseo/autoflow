#!/usr/bin/env python3
"""
Autoflow Test Runner

Automatic test discovery and execution with configurable test suites.
Supports unit tests, integration tests, and custom test patterns.
"""

import argparse
import json
import sys
import unittest
from pathlib import Path


class TestRunner:
    """Test runner with automatic discovery and configurable suites."""

    def __init__(
        self,
        test_dir: str = "tests",
        pattern: str = "test*.py",
        verbose: bool = False
    ):
        """
        Initialize test runner.

        Args:
            test_dir: Directory containing tests
            pattern: File pattern for test discovery
            verbose: Enable verbose output
        """
        self.test_dir = Path(test_dir)
        self.pattern = pattern
        self.verbose = verbose
        self.suites_config = self._load_suites_config()

    def _load_suites_config(self) -> dict:
        """
        Load test suite configuration from config/qa_gates.json.

        Returns:
            Configuration dict with test suite definitions
        """
        config_path = Path("config/qa_gates.json")
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    return config.get("test_suites", {})
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def discover_tests(
        self,
        suite: str | None = None,
        modules: list[str] | None = None
    ) -> unittest.TestSuite:
        """
        Discover tests based on suite or module filters.

        Args:
            suite: Test suite name from configuration
            modules: List of specific test modules to run

        Returns:
            TestSuite with discovered tests
        """
        loader = unittest.TestLoader()

        # If specific modules requested
        if modules:
            suite_obj = unittest.TestSuite()
            for module in modules:
                module_path = self.test_dir / module
                if module_path.exists():
                    tests = loader.loadTestsFromName(
                        f"{module.replace('/', '.')}",
                        module=None
                    )
                    suite_obj.addTests(tests)
            return suite_obj

        # If suite requested
        if suite and suite in self.suites_config:
            suite_config = self.suites_config[suite]
            suite_obj = unittest.TestSuite()

            for pattern in suite_config.get("patterns", []):
                tests = loader.discover(
                    start_dir=str(self.test_dir),
                    pattern=pattern
                )
                suite_obj.addTests(tests)

            return suite_obj

        # Default: discover all tests
        return loader.discover(
            start_dir=str(self.test_dir),
            pattern=self.pattern
        )

    def run_tests(
        self,
        suite: str | None = None,
        modules: list[str] | None = None
    ) -> unittest.TestResult:
        """
        Run tests and return results.

        Args:
            suite: Test suite name from configuration
            modules: List of specific test modules to run

        Returns:
            TestResult with run information
        """
        test_suite = self.discover_tests(suite, modules)

        runner = unittest.TextTestRunner(
            verbosity=2 if self.verbose else 1,
            stream=sys.stdout
        )

        return runner.run(test_suite)

    def list_suites(self) -> None:
        """List available test suites from configuration."""
        if not self.suites_config:
            print("No test suites configured in config/qa_gates.json")
            return

        print("Available test suites:")
        for suite_name, suite_config in self.suites_config.items():
            print(f"\n  {suite_name}:")
            print(f"    Description: {suite_config.get('description', 'N/A')}")
            patterns = suite_config.get('patterns', ['test*.py'])
            print(f"    Patterns: {', '.join(patterns)}")


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="run_tests.py",
        description="Autoflow test runner with automatic discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Run all tests
  %(prog)s --suite unit             Run unit test suite
  %(prog)s --module test_example    Run specific test module
  %(prog)s --list-suites            List available test suites
  %(prog)s --verbose                Run with detailed output
        """
    )

    parser.add_argument(
        "--suite",
        "-s",
        help="Test suite to run (from config/qa_gates.json)"
    )

    parser.add_argument(
        "--module",
        "-m",
        action="append",
        dest="modules",
        help="Specific test module to run (can be specified multiple times)"
    )

    parser.add_argument(
        "--list-suites",
        action="store_true",
        help="List available test suites"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--test-dir",
        default="tests",
        help="Directory containing tests (default: tests)"
    )

    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="File pattern for test discovery (default: test*.py)"
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for test runner.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()

    # Validate test directory exists
    if not Path(args.test_dir).exists():
        print(f"Error: Test directory '{args.test_dir}' does not exist", file=sys.stderr)
        return 1

    # Create test runner
    runner = TestRunner(
        test_dir=args.test_dir,
        pattern=args.pattern,
        verbose=args.verbose
    )

    # Handle list-suites
    if args.list_suites:
        runner.list_suites()
        return 0

    # Run tests
    result = runner.run_tests(suite=args.suite, modules=args.modules)

    # Return exit code based on test results
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
