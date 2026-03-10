#!/usr/bin/env python3
"""
Autoflow QA Fix Request Tool

Command-line tool for managing QA findings and generating fix requests.
Integrates with the verification system to create structured fix tasks.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.review.qa_findings import (
    QAFinding,
    QAFindingReport,
    QAFindingsManager,
    SeverityLevel,
)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="qa_fix_request.py",
        description="Autoflow QA findings and fix request management tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input findings.json --show           Display QA findings
  %(prog)s --input findings.json --check          Check if findings block commit
  %(prog)s --input findings.json --critical-only  Show only critical findings
  %(prog)s --add                                  Add a finding interactively
  %(prog)s --merge report1.json report2.json      Merge multiple reports
  %(prog)s --generate-tasks findings.json         Generate fix tasks from findings
        """,
    )

    parser.add_argument("--input", "-i", help="Input QA findings JSON file")

    parser.add_argument(
        "--output", "-o", help="Output file for QA findings (JSON format)"
    )

    parser.add_argument(
        "--show",
        "-s",
        action="store_true",
        help="Display QA findings in human-readable format",
    )

    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check if findings contain blocking issues",
    )

    parser.add_argument(
        "--critical-only",
        action="store_true",
        help="Show only critical and high severity findings",
    )

    parser.add_argument("--by-file", action="store_true", help="Group findings by file")

    parser.add_argument(
        "--add", action="store_true", help="Add a finding interactively"
    )

    parser.add_argument(
        "--merge", nargs="+", metavar="REPORT", help="Merge multiple report files"
    )

    parser.add_argument(
        "--generate-tasks",
        action="store_true",
        help="Generate fix tasks from findings (for future implementation)",
    )

    parser.add_argument("--file", help="File path for --add")

    parser.add_argument("--line", type=int, help="Line number for --add")

    parser.add_argument(
        "--severity",
        choices=["critical", "high", "medium", "low"],
        help="Severity level for --add",
    )

    parser.add_argument(
        "--category", help="Category for --add (e.g., test, coverage, style)"
    )

    parser.add_argument("--message", help="Message for --add")

    parser.add_argument("--suggested-fix", help="Suggested fix for --add")

    parser.add_argument(
        "--work-dir", default=".", help="Working directory (default: .)"
    )

    return parser.parse_args()


def print_finding(finding: QAFinding, show_index: bool = False, index: int = 0) -> None:
    """
    Print a single QA finding.

    Args:
        finding: QAFinding to display
        show_index: Whether to show index number
        index: Index number for the finding
    """
    prefix = f"{index}. " if show_index else ""
    severity_symbol = {
        SeverityLevel.CRITICAL: "🔴",
        SeverityLevel.HIGH: "🟠",
        SeverityLevel.MEDIUM: "🟡",
        SeverityLevel.LOW: "🔵",
    }.get(finding.severity, "⚪")

    print(f"{prefix}{severity_symbol} {finding}")

    if finding.context:
        print(f"   Context: {finding.context}")

    if finding.suggested_fix:
        print(f"   Fix: {finding.suggested_fix}")

    if finding.rule_id:
        print(f"   Rule: {finding.rule_id}")

    print()


def print_report(
    report: QAFindingReport, critical_only: bool = False, by_file: bool = False
) -> None:
    """
    Print QA findings report.

    Args:
        report: QAFindingReport to display
        critical_only: Show only blocking findings
        by_file: Group findings by file
    """
    print("\n" + "=" * 70)
    print("QA FINDINGS REPORT")
    print("=" * 70)

    # Filter findings if requested
    findings = report.get_blocking_findings() if critical_only else report.findings

    if not findings:
        print("\n✓ No QA findings to display")
        return

    # Show summary
    summary = report.get_summary()
    print(f"\nSummary: {summary['total']} total findings")
    print(f"  🔴 Critical: {summary['critical']}")
    print(f"  🟠 High:     {summary['high']}")
    print(f"  🟡 Medium:   {summary['medium']}")
    print(f"  🔵 Low:      {summary['low']}")

    # Group by file if requested
    if by_file:
        print("\n" + "-" * 70)
        print("FINDINGS BY FILE")
        print("-" * 70)

        for file_path in report.get_unique_files():
            file_findings = report.get_findings_by_file(file_path)
            filtered = [f for f in file_findings if f in findings]

            if filtered:
                print(f"\n📄 {file_path}")
                for finding in filtered:
                    print_finding(finding)
    else:
        print("\n" + "-" * 70)
        print("FINDINGS")
        print("-" * 70)

        for i, finding in enumerate(findings, 1):
            print_finding(finding, show_index=True, index=i)

    print("=" * 70)


def check_blocking(report: QAFindingReport) -> int:
    """
    Check if report contains blocking findings.

    Args:
        report: QAFindingReport to check

    Returns:
        Exit code (0 for pass, 1 for blocking findings)
    """
    blocking = report.get_blocking_findings()

    if not blocking:
        print("\n✓ No blocking findings - commit can proceed")
        return 0
    else:
        print(f"\n✗ Found {len(blocking)} blocking finding(s):")
        for finding in blocking:
            print(f"  - {finding}")
        return 1


def add_finding_interactive(args: argparse.Namespace) -> QAFinding:
    """
    Add a finding from command-line arguments or interactively.

    Args:
        args: Parsed command-line arguments

    Returns:
        QAFinding that was created
    """
    # Get values from args or prompt
    file_path = args.file or input("File path: ")
    line = args.line or int(input("Line number: ") or "0")
    severity_str = args.severity or input("Severity (critical/high/medium/low): ")
    category = args.category or input("Category (e.g., test, coverage, style): ")
    message = args.message or input("Message: ")
    suggested_fix = args.suggested_fix or input("Suggested fix (optional): ") or None

    # Create finding
    finding = QAFinding(
        file=file_path,
        line=line,
        severity=SeverityLevel.from_string(severity_str),
        category=category,
        message=message,
        suggested_fix=suggested_fix,
    )

    print(f"\n✓ Added finding: {finding}")

    return finding


def merge_reports(
    input_files: list[str], manager: QAFindingsManager
) -> QAFindingReport:
    """
    Merge multiple report files.

    Args:
        input_files: List of report file paths
        manager: QAFindingsManager instance

    Returns:
        Merged QAFindingReport
    """
    reports = []
    for input_file in input_files:
        try:
            report = manager.load_report(input_file)
            reports.append(report)
            print(f"Loaded: {input_file} ({len(report.findings)} findings)")
        except Exception as e:
            print(f"Error loading {input_file}: {e}", file=sys.stderr)
            sys.exit(1)

    merged = manager.merge_reports(reports, source="merged")
    print(f"Merged: {len(merged.findings)} total findings")

    return merged


def main() -> int:
    """
    Main entry point for QA fix request tool.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()
    manager = QAFindingsManager(work_dir=args.work_dir)

    # Handle merge operation
    if args.merge:
        report = merge_reports(args.merge, manager)

        if args.output:
            manager.save_report(report, args.output)
            print(f"\n✓ Merged report saved to: {args.output}")
        else:
            print_report(report, critical_only=args.critical_only, by_file=args.by_file)

        return 0

    # Handle add finding
    if args.add:
        finding = add_finding_interactive(args)

        # Create or load report
        if args.input:
            try:
                report = manager.load_report(args.input)
            except Exception:
                report = manager.create_report()
        else:
            report = manager.create_report()

        report.add_finding(finding)

        # Save report
        output_path = args.output or args.input or "qa_findings.json"
        manager.save_report(report, output_path)
        print(f"✓ Report saved to: {output_path}")

        return 0

    # Handle show/check operations (require input)
    if not args.input:
        print("Error: --input is required for --show and --check", file=sys.stderr)
        return 1

    try:
        report = manager.load_report(args.input)
    except Exception as e:
        print(f"Error loading report: {e}", file=sys.stderr)
        return 1

    # Show report
    if args.show:
        print_report(report, critical_only=args.critical_only, by_file=args.by_file)

    # Check for blocking findings
    if args.check:
        return check_blocking(report)

    # If no action specified, default to show
    if not args.show and not args.check:
        print_report(report, critical_only=args.critical_only, by_file=args.by_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
