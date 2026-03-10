#!/usr/bin/env python3
"""
Autoflow Fix Task Generator

Command-line tool for parsing QA findings and generating fix tasks.
Integrates with the verification system to create structured tasks from failures.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.review.qa_findings import QAFinding, QAFindingReport, QAFindingsManager


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="generate_fix_tasks.py",
        description="Autoflow fix task generator for QA findings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input findings.json                    Generate tasks from findings
  %(prog)s --input findings.json --blocking-only    Only generate tasks for blocking issues
  %(prog)s --input findings.json --output tasks/    Custom output directory
  %(prog)s --input findings.json --dry-run          Show what would be generated
  %(prog)s --list-tasks                             List existing fix tasks
        """,
    )

    parser.add_argument("--input", "-i", help="Input QA findings JSON file")

    parser.add_argument(
        "--output",
        "-o",
        default=".autoflow/tasks",
        help="Output directory for fix tasks (default: .autoflow/tasks)",
    )

    parser.add_argument(
        "--blocking-only",
        "-b",
        action="store_true",
        help="Only generate tasks for blocking findings (CRITICAL and HIGH)",
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be generated without creating files",
    )

    parser.add_argument(
        "--list-tasks",
        "-l",
        action="store_true",
        help="List existing fix tasks in output directory",
    )

    parser.add_argument(
        "--severity",
        "-s",
        choices=["critical", "high", "medium", "low"],
        help="Filter findings by severity level",
    )

    parser.add_argument(
        "--category",
        "-c",
        help="Filter findings by category (e.g., test, coverage, style)",
    )

    parser.add_argument(
        "--agent",
        "-a",
        default="implementation-runner",
        help="Agent to assign fix tasks to (default: implementation-runner)",
    )

    parser.add_argument(
        "--work-dir", default=".", help="Working directory (default: .)"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    return parser.parse_args()


def generate_task_id(finding: QAFinding, index: int) -> str:
    """
    Generate a unique task ID from a QA finding.

    Args:
        finding: QAFinding to generate ID from
        index: Index of the finding

    Returns:
        Unique task ID string
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    category = finding.category.lower()
    severity = finding.severity.value.lower()

    # Create a short identifier from file path
    file_id = finding.file.replace("/", "_").replace(".", "_")
    if len(file_id) > 30:
        file_id = file_id[-30:]

    return f"fix-{category}-{severity}-{timestamp}-{index:03d}-{file_id}"


def create_fix_task(
    finding: QAFinding, task_id: str, agent: str = "implementation-runner"
) -> dict:
    """
    Create a fix task from a QA finding.

    Args:
        finding: QAFinding to convert
        task_id: Unique task identifier
        agent: Agent to assign the task to

    Returns:
        Task dictionary
    """
    task = {
        "task_id": task_id,
        "type": "fix",
        "status": "pending",
        "priority": finding.severity.value,
        "agent": agent,
        "created_at": datetime.now().isoformat(),
        "title": f"Fix {finding.category} issue in {finding.file}:{finding.line}",
        "description": finding.message,
        "finding": {
            "file": finding.file,
            "line": finding.line,
            "column": finding.column,
            "severity": finding.severity.value,
            "category": finding.category,
            "message": finding.message,
            "suggested_fix": finding.suggested_fix,
            "context": finding.context,
            "rule_id": finding.rule_id,
        },
        "actions": [],
    }

    # Add suggested fix as an action if available
    if finding.suggested_fix:
        task["actions"].append(
            {
                "type": "apply_fix",
                "description": finding.suggested_fix,
                "file": finding.file,
                "line": finding.line,
            }
        )

    # Add verification action
    task["actions"].append(
        {
            "type": "verify",
            "description": "Run tests and checks to verify the fix",
            "command": "python scripts/run_tests.py",
        }
    )

    return task


def save_task(task: dict, output_dir: Path, task_id: str) -> None:
    """
    Save a fix task to a JSON file.

    Args:
        task: Task dictionary to save
        output_dir: Directory to save the task in
        task_id: Unique task identifier
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    task_file = output_dir / f"{task_id}.json"

    with open(task_file, "w") as f:
        json.dump(task, f, indent=2)


def load_tasks(output_dir: Path) -> list[dict]:
    """
    Load all fix tasks from output directory.

    Args:
        output_dir: Directory containing task files

    Returns:
        List of task dictionaries
    """
    tasks = []

    if not output_dir.exists():
        return tasks

    for task_file in output_dir.glob("*.json"):
        try:
            with open(task_file) as f:
                task = json.load(f)
                tasks.append(task)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load {task_file}: {e}", file=sys.stderr)

    # Sort by created_at
    tasks.sort(key=lambda t: t.get("created_at", ""))

    return tasks


def print_task_summary(task: dict, show_index: bool = False, index: int = 0) -> None:
    """
    Print a summary of a fix task.

    Args:
        task: Task dictionary to display
        show_index: Whether to show index number
        index: Index number for the task
    """
    prefix = f"{index}. " if show_index else ""

    priority_symbol = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(
        task.get("priority", "low"), "⚪"
    )

    status_symbol = {
        "pending": "📋",
        "in_progress": "⚙️",
        "completed": "✅",
        "blocked": "🚫",
    }.get(task.get("status", "pending"), "📋")

    print(f"{prefix}{status_symbol} {priority_symbol} {task['task_id']}")
    print(f"   Title: {task.get('title', 'N/A')}")

    finding = task.get("finding", {})
    if finding:
        location = f"{finding.get('file', 'N/A')}:{finding.get('line', 0)}"
        print(f"   Location: {location}")
        print(f"   Category: {finding.get('category', 'N/A')}")

    print(f"   Agent: {task.get('agent', 'N/A')}")
    print(f"   Status: {task.get('status', 'pending')}")
    print()


def print_tasks_summary(tasks: list[dict]) -> None:
    """
    Print summary of fix tasks.

    Args:
        tasks: List of task dictionaries
    """
    print("\n" + "=" * 70)
    print("FIX TASKS SUMMARY")
    print("=" * 70)

    if not tasks:
        print("\n✓ No fix tasks found")
        return

    # Count by status
    status_counts = {}
    priority_counts = {}

    for task in tasks:
        status = task.get("status", "pending")
        priority = task.get("priority", "low")

        status_counts[status] = status_counts.get(status, 0) + 1
        priority_counts[priority] = priority_counts.get(priority, 0) + 1

    print(f"\nTotal Tasks: {len(tasks)}")
    print("\nBy Status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    print("\nBy Priority:")
    for priority, count in sorted(priority_counts.items()):
        symbol = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(
            priority, "⚪"
        )
        print(f"  {symbol} {priority}: {count}")

    print("\n" + "=" * 70)


def filter_findings(
    findings: list[QAFinding],
    blocking_only: bool = False,
    severity_filter: str | None = None,
    category_filter: str | None = None,
) -> list[QAFinding]:
    """
    Filter findings based on criteria.

    Args:
        findings: List of findings to filter
        blocking_only: Only include blocking findings
        severity_filter: Only include findings with this severity
        category_filter: Only include findings with this category

    Returns:
        Filtered list of findings
    """
    filtered = findings

    if blocking_only:
        filtered = [f for f in filtered if f.severity.blocks_commit()]

    if severity_filter:
        filtered = [f for f in filtered if f.severity.value == severity_filter]

    if category_filter:
        filtered = [f for f in filtered if f.category == category_filter]

    return filtered


def generate_tasks_from_findings(
    report: QAFindingReport,
    output_dir: Path,
    agent: str,
    blocking_only: bool = False,
    severity_filter: str | None = None,
    category_filter: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Generate fix tasks from QA findings report.

    Args:
        report: QAFindingReport with findings
        output_dir: Directory to save tasks in
        agent: Agent to assign tasks to
        blocking_only: Only generate tasks for blocking findings
        severity_filter: Filter by severity level
        category_filter: Filter by category
        dry_run: Show what would be generated without creating files
        verbose: Enable verbose output

    Returns:
        Number of tasks generated
    """
    findings = filter_findings(
        report.findings, blocking_only, severity_filter, category_filter
    )

    if not findings:
        print("\n✓ No findings match the specified criteria")
        return 0

    print(f"\nGenerating fix tasks for {len(findings)} finding(s)...\n")

    generated_count = 0

    for i, finding in enumerate(findings, 1):
        task_id = generate_task_id(finding, i)
        task = create_fix_task(finding, task_id, agent)

        if dry_run:
            print(f"Would create: {task_id}.json")
            if verbose:
                print_task_summary(task, show_index=True, index=i)
        else:
            save_task(task, output_dir, task_id)
            generated_count += 1
            print(f"✓ Created: {task_id}.json")
            if verbose:
                print_task_summary(task, show_index=True, index=i)

    return generated_count


def list_existing_tasks(output_dir: Path) -> int:
    """
    List existing fix tasks in output directory.

    Args:
        output_dir: Directory containing task files

    Returns:
        Exit code (0 for success, 1 for error)
    """
    tasks = load_tasks(output_dir)

    print_tasks_summary(tasks)

    if tasks:
        print("\nTASKS:")
        print("-" * 70)

        for i, task in enumerate(tasks, 1):
            print_task_summary(task, show_index=True, index=i)

    return 0


def main() -> int:
    """
    Main entry point for fix task generator.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()
    work_dir = Path(args.work_dir)
    output_dir = work_dir / args.output

    # Handle list-tasks operation
    if args.list_tasks:
        return list_existing_tasks(output_dir)

    # Require input for task generation
    if not args.input:
        print("Error: --input is required for task generation", file=sys.stderr)
        print("Use --list-tasks to list existing tasks without input", file=sys.stderr)
        return 1

    # Load QA findings
    manager = QAFindingsManager(work_dir=str(work_dir))

    try:
        report = manager.load_report(args.input)
    except Exception as e:
        print(f"Error loading QA findings: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Loaded QA findings from: {args.input}")
        print(f"Total findings: {len(report.findings)}")

    # Show report summary
    summary = report.get_summary()
    print("\nQA Findings Summary:")
    print(f"  Total: {summary['total']}")
    print(f"  🔴 Critical: {summary['critical']}")
    print(f"  🟠 High:     {summary['high']}")
    print(f"  🟡 Medium:   {summary['medium']}")
    print(f"  🔵 Low:      {summary['low']}")

    # Generate tasks
    try:
        count = generate_tasks_from_findings(
            report=report,
            output_dir=output_dir,
            agent=args.agent,
            blocking_only=args.blocking_only,
            severity_filter=args.severity,
            category_filter=args.category,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        if args.dry_run:
            print(f"\nDry run complete. Would generate {count} task(s).")
        else:
            print(f"\n✓ Generated {count} fix task(s)")
            print(f"  Output directory: {output_dir}")

        return 0

    except Exception as e:
        print(f"Error generating tasks: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
