#!/usr/bin/env python3
"""
Autoflow Coverage Report Tool

Command-line tool for running coverage analysis and generating reports.
Integrates with the verification system to check coverage thresholds.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.review.coverage import CoverageReport, CoverageThreshold, CoverageTracker


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="coverage_report.py",
        description="Autoflow coverage analysis and reporting tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Run coverage and display report
  %(prog)s --check                  Check coverage against thresholds
  %(prog)s --output report.json     Save coverage report to file
  %(prog)s --source autoflow,utils  Measure specific directories
  %(prog)s --min-coverage 90        Require 90%% minimum coverage
  %(prog)s --show-files             Show per-file coverage breakdown
        """
    )

    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check coverage against configured thresholds"
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Output file for coverage report (JSON format)"
    )

    parser.add_argument(
        "--source",
        "-s",
        default="autoflow",
        help="Comma-separated list of source directories to measure (default: autoflow)"
    )

    parser.add_argument(
        "--test-command",
        default="python -m unittest discover tests/",
        help="Command to run tests (default: 'python -m unittest discover tests/')"
    )

    parser.add_argument(
        "--min-coverage",
        type=float,
        help="Override minimum coverage threshold (default: from config)"
    )

    parser.add_argument(
        "--config",
        help="Path to QA gates configuration file"
    )

    parser.add_argument(
        "--show-files",
        "-f",
        action="store_true",
        help="Show per-file coverage breakdown"
    )

    parser.add_argument(
        "--show-uncovered",
        action="store_true",
        help="Show files with zero or low coverage"
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=80.0,
        help="Coverage threshold for --show-uncovered (default: 80.0)"
    )

    parser.add_argument(
        "--work-dir",
        default=".",
        help="Working directory for coverage execution (default: .)"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output"
    )

    return parser.parse_args()


def print_report(report: CoverageReport, show_files: bool = False) -> None:
    """
    Print coverage report to stdout.

    Args:
        report: CoverageReport to display
        show_files: Whether to show per-file breakdown
    """
    print("\n" + "=" * 60)
    print("COVERAGE REPORT")
    print("=" * 60)

    print(f"\nTotal Coverage: {report.total:.1f}%")

    if report.branches is not None:
        print(f"Branch Coverage: {report.branches:.1f}%")
    if report.functions is not None:
        print(f"Function Coverage: {report.functions:.1f}%")
    if report.lines is not None:
        print(f"Line Coverage: {report.lines:.1f}%")

    if show_files and report.files:
        print("\n" + "-" * 60)
        print("PER-FILE COVERAGE")
        print("-" * 60)

        # Sort files by coverage
        sorted_files = sorted(
            report.files.items(),
            key=lambda x: x[1],
            reverse=True
        )

        for filename, coverage in sorted_files:
            status = "✓" if coverage >= 80.0 else "✗"
            print(f"  {status} {filename:50s} {coverage:5.1f}%")

    print("\n" + "=" * 60)


def print_uncovered_files(
    tracker: CoverageTracker,
    report: CoverageReport,
    threshold: float
) -> None:
    """
    Print files below coverage threshold.

    Args:
        tracker: CoverageTracker instance
        report: CoverageReport to analyze
        threshold: Coverage threshold
    """
    low_coverage = tracker.get_low_coverage_files(report, threshold)

    if not low_coverage:
        print(f"\n✓ All files meet {threshold:.1f}% coverage threshold")
        return

    print(f"\nFiles below {threshold:.1f}% coverage:")
    print("-" * 60)

    for filename, coverage in low_coverage:
        print(f"  {filename:50s} {coverage:5.1f}%")


def check_thresholds(
    tracker: CoverageTracker,
    report: CoverageReport
) -> int:
    """
    Check coverage against thresholds and return exit code.

    Args:
        tracker: CoverageTracker instance
        report: CoverageReport to check

    Returns:
        Exit code (0 for pass, 1 for fail)
    """
    passes, failing = tracker.check_thresholds(report)

    if passes:
        print("\n✓ Coverage meets all thresholds")
        return 0
    else:
        print("\n✗ Coverage thresholds not met:")
        for metric in failing:
            print(f"  - {metric}")
        return 1


def main() -> int:
    """
    Main entry point for coverage report tool.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()

    # Create coverage tracker
    tracker = CoverageTracker(
        config_path=args.config,
        work_dir=args.work_dir
    )

    # Override threshold if specified
    if args.min_coverage is not None:
        tracker.threshold = CoverageThreshold(minimum=args.min_coverage)

    # Run coverage
    if args.verbose:
        print("Running coverage analysis...")
        print(f"  Source: {args.source}")
        print(f"  Test command: {args.test_command}")

    source_dirs = [s.strip() for s in args.source.split(",")]
    exit_code, output = tracker.run_coverage(
        test_command=args.test_command,
        source_dirs=source_dirs
    )

    if exit_code != 0:
        print("Error running tests:", file=sys.stderr)
        print(output, file=sys.stderr)
        return 1

    if args.verbose:
        print("Tests completed successfully")
        print("Generating coverage report...\n")

    # Generate report
    try:
        report = tracker.generate_report()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Display report
    print_report(report, show_files=args.show_files)

    # Show uncovered files if requested
    if args.show_uncovered:
        print_uncovered_files(tracker, report, args.threshold)

    # Save report if output path specified
    if args.output:
        tracker.save_report(report, args.output)
        print(f"\nCoverage report saved to: {args.output}")

    # Check thresholds if requested
    if args.check:
        return check_thresholds(tracker, report)

    # Return success if not checking thresholds
    return 0


if __name__ == "__main__":
    sys.exit(main())
