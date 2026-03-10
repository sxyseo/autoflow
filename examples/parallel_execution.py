#!/usr/bin/env python3
"""
Autoflow Parallel Execution Example

This script demonstrates how to use the parallel execution capabilities
to run multiple AI agents concurrently on independent tasks.

Usage examples:
    # Show available commands
    python examples/parallel_execution.py --help

    # Run a simple parallel execution with 3 tasks
    python examples/parallel_execution.py run-basic

    # Run parallel execution with custom task count
    python examples/parallel_execution.py run-basic --tasks 5

    # Demonstrate conflict detection
    python examples/parallel_execution.py detect-conflicts

    # Show coordinator statistics
    python examples/parallel_execution.py stats

    # Run with custom configuration
    python examples/parallel_execution.py run-basic --max-parallel 5 --timeout 600
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoflow.core.parallel import (
    ParallelCoordinator,
    ParallelExecutionResult,
    create_parallel_coordinator,
)
from autoflow.core.config import load_config


ROOT = Path(__file__).resolve().parent.parent


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_result_summary(result: ParallelExecutionResult) -> None:
    """Print a summary of parallel execution results."""
    summary = result.get_summary()
    print(f"\n📊 Execution Summary:")
    print(f"  Group ID: {result.group_id}")
    print(f"  Total Tasks: {summary['total_tasks']}")
    print(f"  Successful: {summary['successful_tasks']}")
    print(f"  Failed: {summary['failed_tasks']}")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    print(f"  Success Rate: {summary['success_rate']}%")

    if result.conflict_report and summary['conflicts_detected']:
        print(f"  ⚠️  Conflicts Detected: {summary['high_severity_conflicts']} high-severity")

    if result.task_results:
        print(f"\n📋 Task Results:")
        for task_id, task_result in result.task_results.items():
            status = "✅" if task_result.success else "❌"
            duration = f"{task_result.duration_seconds:.2f}s" if task_result.duration_seconds else "N/A"
            print(f"  {status} {task_id} ({duration})")
            if task_result.error:
                print(f"     Error: {task_result.error[:100]}{'...' if len(task_result.error) > 100 else ''}")


def create_sample_tasks(count: int = 3) -> list[dict[str, Any]]:
    """Create sample tasks for demonstration."""
    task_templates = [
        {"task": "Fix bug in authentication module", "workdir": "./src/auth"},
        {"task": "Update API documentation", "workdir": "./docs/api"},
        {"task": "Add unit tests for user service", "workdir": "./tests/user"},
        {"task": "Refactor database connection logic", "workdir": "./src/db"},
        {"task": "Implement new feature flags", "workdir": "./src/features"},
        {"task": "Optimize query performance", "workdir": "./src/queries"},
        {"task": "Review and fix security issues", "workdir": "./src/security"},
        {"task": "Update dependency versions", "workdir": "./"},
    ]

    # Add unique IDs to tasks
    tasks = []
    for i in range(min(count, len(task_templates))):
        task_data = task_templates[i].copy()
        task_data["id"] = f"task-{i + 1}"
        tasks.append(task_data)

    return tasks


def create_conflicting_tasks() -> list[dict[str, Any]]:
    """Create tasks that will trigger conflict detection."""
    return [
        {"id": "task-1", "task": "Fix bug in auth.py", "workdir": "./src/auth"},
        {"id": "task-2", "task": "Add feature to auth.py", "workdir": "./src/auth"},
        {"id": "task-3", "task": "Update tests in test_auth.py", "workdir": "./tests/auth"},
        {"id": "task-4", "task": "Modify auth.py again", "workdir": "./src/auth"},
    ]


async def cmd_run_basic(args: argparse.Namespace) -> None:
    """Run a basic parallel execution example."""
    print_section("Basic Parallel Execution Example")

    task_count = args.tasks or 3
    max_parallel = args.max_parallel or 3
    timeout = args.timeout or 300

    print(f"Configuration:")
    print(f"  Max Parallel Tasks: {max_parallel}")
    print(f"  Timeout per Task: {timeout}s")
    print(f"  Task Count: {task_count}")

    # Create sample tasks
    tasks = create_sample_tasks(task_count)
    print(f"\n📝 Tasks to Execute:")
    for task in tasks:
        print(f"  • [{task['id']}] {task['task']} ({task.get('workdir', 'N/A')})")

    # Create coordinator
    coordinator = create_parallel_coordinator(
        max_parallel=max_parallel,
        state_dir=".autoflow",
    )

    print(f"\n🚀 Starting Parallel Execution...")
    start_time = datetime.now()

    try:
        # Execute tasks in parallel
        result = await coordinator.execute_parallel(
            tasks=tasks,
            check_conflicts=True,
            timeout_seconds=timeout,
        )

        end_time = datetime.now()
        print(f"\n✅ Execution completed in {(end_time - start_time).total_seconds():.2f}s")

        # Print results
        print_result_summary(result)

        # Show aggregated output if available
        if result.get_aggregated_output():
            print(f"\n📄 Aggregated Output:")
            output = result.get_aggregated_output()
            # Truncate very long output
            if len(output) > 500:
                output = output[:500] + "\n... (truncated)"
            print(output)

        # Show errors if any
        errors = result.get_aggregated_errors()
        if errors:
            print(f"\n⚠️  Errors:")
            for error in errors:
                print(f"  {error}")

    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        sys.exit(1)


async def cmd_detect_conflicts(args: argparse.Namespace) -> None:
    """Demonstrate conflict detection."""
    print_section("Conflict Detection Example")

    tasks = create_conflicting_tasks()

    print(f"📝 Tasks with Potential Conflicts:")
    for task in tasks:
        print(f"  • [{task['id']}] {task['task']} ({task.get('workdir', 'N/A')})")

    # Create coordinator
    coordinator = create_parallel_coordinator(
        max_parallel=3,
        state_dir=".autoflow",
    )

    print(f"\n🔍 Running Conflict Detection...")

    try:
        # This should detect conflicts
        result = await coordinator.execute_parallel(
            tasks=tasks,
            check_conflicts=True,
            timeout_seconds=300,
        )

        print_result_summary(result)

        if result.conflict_report:
            print(f"\n🚫 Conflict Report:")
            conflicts = result.conflict_report.get_high_severity()
            if conflicts:
                for conflict in conflicts[:5]:  # Show first 5
                    print(f"  • {conflict.get('type', 'Unknown')}: {conflict.get('description', 'No description')}")
            else:
                print("  No high-severity conflicts detected")

    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        sys.exit(1)


async def cmd_stats(args: argparse.Namespace) -> None:
    """Show coordinator statistics."""
    print_section("Coordinator Statistics")

    # Create coordinator (but don't execute anything)
    coordinator = create_parallel_coordinator(
        max_parallel=args.max_parallel or 3,
        state_dir=".autoflow",
    )

    # Get statistics
    stats = coordinator.get_stats_summary()

    print(f"📊 Coordinator Statistics:")
    print(f"  Max Parallel Tasks: {stats['max_parallel']}")
    print(f"  Active Tasks: {stats['active_tasks']}")
    print(f"  Available Slots: {stats['available_slots']}")
    print(f"  Total Groups Executed: {stats['total_groups']}")
    print(f"  Successful Groups: {stats['successful_groups']}")
    print(f"  Failed Groups: {stats['failed_groups']}")
    print(f"  Total Tasks: {stats['total_tasks']}")
    print(f"  Completed Tasks: {stats['completed_tasks']}")
    print(f"  Failed Tasks: {stats['failed_tasks']}")
    print(f"  Avg Group Duration: {stats['average_group_duration']:.2f}s")
    print(f"  Last Execution: {stats['last_execution_at'] or 'Never'}")
    print(f"  Started At: {stats['started_at']}")

    # Show capacity information
    print(f"\n💪 Capacity Information:")
    if coordinator.check_capacity_available(3):
        print(f"  ✅ Can run 3 concurrent tasks")
    else:
        print(f"  ⚠️  Insufficient capacity for 3 concurrent tasks")

    if coordinator.check_capacity_available(5):
        print(f"  ✅ Can run 5 concurrent tasks")
    else:
        print(f"  ⚠️  Insufficient capacity for 5 concurrent tasks")


async def cmd_configuration(args: argparse.Namespace) -> None:
    """Show configuration information."""
    print_section("Configuration Example")

    config_path = args.config or "config/parallel.example.json5"
    config_file = ROOT / config_path

    if not config_file.exists():
        print(f"⚠️  Configuration file not found: {config_path}")
        print(f"Using default configuration:")
        default_config = {
            "enabled": False,
            "max_concurrent_tasks": 3,
            "timeout_seconds": 300,
        }
        print(json.dumps(default_config, indent=2))
        return

    try:
        # Try to load as JSON (strip JSON5 comments for simple cases)
        content = config_file.read_text(encoding="utf-8")
        # Simple JSON5 comment removal (not a full parser)
        lines = []
        for line in content.split('\n'):
            # Remove // comments
            if '//' in line:
                line = line[:line.index('//')]
            # Remove /* */ comments (simple case)
            if '/*' in line and '*/' in line:
                start = line.index('/*')
                end = line.index('*/') + 2
                line = line[:start] + line[end:]
            lines.append(line)
        cleaned_content = '\n'.join(lines)

        config_data = json.loads(cleaned_content)

        print(f"📁 Configuration from: {config_path}")
        print(f"\n📋 Current Settings:")
        print(json.dumps(config_data, indent=2))

        print(f"\n💡 Configuration Tips:")
        print(f"  • Copy config/parallel.example.json5 to config/parallel.json5")
        print(f"  • Set 'enabled: true' to activate parallel execution")
        print(f"  • Adjust 'max_concurrent_tasks' based on your system resources")
        print(f"  • Increase 'timeout_seconds' for long-running tasks")

    except json.JSONDecodeError as e:
        print(f"⚠️  Could not parse configuration file: {e}")
        print(f"Note: This example uses simple JSON5 parsing.")
    except Exception as e:
        print(f"⚠️  Error loading configuration: {e}")


async def cmd_examples(args: argparse.Namespace) -> None:
    """Show usage examples."""
    print_section("Usage Examples")

    examples = [
        {
            "title": "Basic Parallel Execution",
            "description": "Run 3 tasks in parallel with default settings",
            "command": "python examples/parallel_execution.py run-basic",
        },
        {
            "title": "Custom Task Count",
            "description": "Run 5 tasks in parallel",
            "command": "python examples/parallel_execution.py run-basic --tasks 5",
        },
        {
            "title": "Custom Parallelism",
            "description": "Run with 5 concurrent tasks",
            "command": "python examples/parallel_execution.py run-basic --max-parallel 5 --tasks 10",
        },
        {
            "title": "Longer Timeout",
            "description": "Run with 10-minute timeout per task",
            "command": "python examples/parallel_execution.py run-basic --timeout 600",
        },
        {
            "title": "Conflict Detection",
            "description": "Demonstrate conflict detection between tasks",
            "command": "python examples/parallel_execution.py detect-conflicts",
        },
        {
            "title": "View Statistics",
            "description": "Show coordinator statistics and capacity",
            "command": "python examples/parallel_execution.py stats",
        },
        {
            "title": "View Configuration",
            "description": "Show current parallel execution configuration",
            "command": "python examples/parallel_execution.py configuration",
        },
    ]

    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['title']}")
        print(f"   {example['description']}")
        print(f"   $ {example['command']}")

    print(f"\n💡 Tips:")
    print(f"  • Use --help with any command to see more options")
    print(f"  • Adjust max-parallel based on your CPU cores and memory")
    print(f"  • Start with smaller task counts to test your setup")
    print(f"  • Enable conflict detection when tasks might share files")


def main() -> None:
    """Main entry point for the parallel execution example."""
    parser = argparse.ArgumentParser(
        description="Autoflow Parallel Execution Examples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Global options
    parser.add_argument(
        "--max-parallel",
        type=int,
        help="Maximum number of concurrent tasks",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="Timeout in seconds for each task",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run-basic command
    basic_parser = subparsers.add_parser(
        "run-basic",
        help="Run a basic parallel execution example",
    )
    basic_parser.add_argument(
        "--tasks",
        type=int,
        default=3,
        help="Number of tasks to execute (default: 3)",
    )

    # detect-conflicts command
    subparsers.add_parser(
        "detect-conflicts",
        help="Demonstrate conflict detection",
    )

    # stats command
    subparsers.add_parser(
        "stats",
        help="Show coordinator statistics",
    )

    # configuration command
    subparsers.add_parser(
        "configuration",
        help="Show configuration information",
    )

    # examples command
    subparsers.add_parser(
        "examples",
        help="Show usage examples",
    )

    args = parser.parse_args()

    # If no command, show help
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Execute command
    command_handlers = {
        "run-basic": cmd_run_basic,
        "detect-conflicts": cmd_detect_conflicts,
        "stats": cmd_stats,
        "configuration": cmd_configuration,
        "examples": cmd_examples,
    }

    handler = command_handlers.get(args.command)
    if handler:
        # Use asyncio to run async commands
        asyncio.run(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
