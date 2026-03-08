"""Autoflow Analytics CLI

Provides command-line interface for analytics features:
- Velocity metrics and task completion tracking
- Quality trends and test pass rates
- Agent performance comparison
- ROI measurements and time saved
- Export reports in multiple formats

Usage:
    autoflow analytics --help
    autoflow analytics velocity --days 7
    autoflow analytics quality --trend
    autoflow analytics agents --compare
    autoflow analytics export --format json --output report.json
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import click

from autoflow.analytics import (
    AgentPerformance,
    MetricsCollector,
    QualityTrends,
    ROICalculator,
    VelocityTracker,
)


# Click context settings
CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 120,
}


def _print_json(data: Any, indent: int = 2) -> None:
    """Print data as formatted JSON."""
    click.echo(json.dumps(data, indent=indent, default=str))


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def _format_percentage(value: float) -> str:
    """Format a percentage value."""
    return f"{value:.1f}%"


@click.group(
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Increase verbosity (can be used multiple times).",
)
@click.pass_context
def analytics(
    ctx: click.Context,
    output_json: bool,
    verbose: int,
) -> None:
    """
    Autoflow Analytics - Performance insights for autonomous development.

    Provides comprehensive analytics and performance tracking for the Autoflow system,
    including velocity metrics, quality trends, agent performance, and ROI measurements.

    \b
    Quick Start:
        autoflow analytics velocity          # Show velocity metrics
        autoflow analytics quality           # Show quality trends
        autoflow analytics agents            # Show agent performance
        autoflow analytics export            # Export analytics report

    \b
    Examples:
        autoflow analytics velocity --days 7
        autoflow analytics quality --trend --days 30
        autoflow analytics agents --compare claude-code codex
        autoflow analytics export --format json --output report.json

    For more information, visit: https://github.com/autoflow/autoflow
    """
    ctx.ensure_object(dict)

    # Store options in context
    ctx.obj["output_json"] = output_json
    ctx.obj["verbose"] = verbose


# === Velocity Command ===

@analytics.command()
@click.option(
    "--days",
    "-d",
    type=int,
    default=7,
    help="Number of days to analyze (default: 7).",
)
@click.option(
    "--trend",
    is_flag=True,
    help="Show trend over time.",
)
@click.pass_context
def velocity(
    ctx: click.Context,
    days: int,
    trend: bool,
) -> None:
    """
    Show velocity metrics.

    Displays task completion rates, cycle times, and throughput metrics
    for the specified time period.

    \b
    Metrics shown:
        - Tasks completed
        - Average cycle time
        - Tasks per day
        - Completion rate
    """
    tracker = VelocityTracker()

    try:
        # Get velocity metrics
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        metrics = tracker.get_velocity_metrics(
            start_date=start_date,
            end_date=end_date,
        )

        if ctx.obj["output_json"]:
            _print_json({
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": days,
                },
                "metrics": {
                    "tasks_completed": metrics.tasks_completed,
                    "average_cycle_time_hours": metrics.average_cycle_time_hours,
                    "tasks_per_day": metrics.tasks_per_day,
                    "completion_rate": metrics.completion_rate,
                },
            })
            return

        # Human-readable output
        click.echo(f"Velocity Metrics (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Tasks Completed: {metrics.tasks_completed}")
        click.echo(f"Avg Cycle Time: {_format_duration(metrics.average_cycle_time_hours * 3600)}")
        click.echo(f"Tasks Per Day: {metrics.tasks_per_day:.1f}")
        click.echo(f"Completion Rate: {_format_percentage(metrics.completion_rate)}")

        if trend:
            click.echo("\nTrend:")
            trend_data = tracker.get_velocity_trend(
                start_date=start_date,
                end_date=end_date,
                bucket_days=max(1, days // 10),
            )

            for data_point in trend_data[:5]:  # Show first 5 data points
                click.echo(
                    f"  {_format_datetime(data_point.date)}: "
                    f"{data_point.tasks_completed} tasks, "
                    f"{_format_duration(data_point.average_cycle_time_hours * 3600)} avg cycle time"
                )

    except Exception as e:
        click.echo(f"Error retrieving velocity metrics: {e}", err=True)
        if ctx.obj["verbose"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


# === Quality Command ===

@analytics.command()
@click.option(
    "--days",
    "-d",
    type=int,
    default=7,
    help="Number of days to analyze (default: 7).",
)
@click.option(
    "--trend",
    is_flag=True,
    help="Show trend over time.",
)
@click.pass_context
def quality(
    ctx: click.Context,
    days: int,
    trend: bool,
) -> None:
    """
    Show quality trends.

    Displays test pass rates, review outcomes, and quality metrics
    for the specified time period.

    \b
    Metrics shown:
        - Test pass rate
        - Test count
        - Review approval rate
        - Review count
        - Quality score
    """
    trends = QualityTrends()

    try:
        # Get quality metrics
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        metrics = trends.get_quality_metrics(
            start_date=start_date,
            end_date=end_date,
        )

        if ctx.obj["output_json"]:
            _print_json({
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": days,
                },
                "metrics": {
                    "test_pass_rate": metrics.test_pass_rate,
                    "test_count": metrics.test_count,
                    "review_approval_rate": metrics.review_approval_rate,
                    "review_count": metrics.review_count,
                    "quality_score": metrics.quality_score,
                },
            })
            return

        # Human-readable output
        click.echo(f"Quality Trends (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Test Pass Rate: {_format_percentage(metrics.test_pass_rate)}")
        click.echo(f"Test Count: {metrics.test_count}")
        click.echo(f"Review Approval Rate: {_format_percentage(metrics.review_approval_rate)}")
        click.echo(f"Review Count: {metrics.review_count}")
        click.echo(f"Quality Score: {metrics.quality_score:.1f}/100")

        if trend:
            click.echo("\nTrend:")
            trend_data = trends.get_quality_trend(
                start_date=start_date,
                end_date=end_date,
                bucket_days=max(1, days // 10),
            )

            for data_point in trend_data[:5]:  # Show first 5 data points
                click.echo(
                    f"  {_format_datetime(data_point.date)}: "
                    f"{_format_percentage(data_point.test_pass_rate)} pass rate, "
                    f"{data_point.quality_score:.1f} quality score"
                )

    except Exception as e:
        click.echo(f"Error retrieving quality metrics: {e}", err=True)
        if ctx.obj["verbose"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


# === Agents Command ===

@analytics.command()
@click.option(
    "--compare",
    "-c",
    multiple=True,
    type=str,
    help="Compare specific agents (can be specified multiple times).",
)
@click.option(
    "--days",
    "-d",
    type=int,
    default=7,
    help="Number of days to analyze (default: 7).",
)
@click.pass_context
def agents(
    ctx: click.Context,
    compare: tuple[str, ...],
    days: int,
) -> None:
    """
    Show agent performance.

    Displays execution statistics, success rates, and performance metrics
    for AI agents.

    \b
    Metrics shown:
        - Total executions
        - Success rate
        - Average duration
        - Error rate
    """
    perf = AgentPerformance()

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        if compare:
            # Compare specific agents
            agent_names = list(compare)
        else:
            # Show all agents
            summary = perf.get_all_agents_summary(
                start_date=start_date,
                end_date=end_date,
            )
            agent_names = [s.agent_name for s in summary]

        if ctx.obj["output_json"]:
            comparison = perf.compare_agents(
                agent_names=agent_names,
                start_date=start_date,
                end_date=end_date,
            )

            _print_json({
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": days,
                },
                "agents": comparison,
            })
            return

        # Human-readable output
        click.echo(f"Agent Performance (Last {days} days)")
        click.echo("=" * 60)

        for agent_name in agent_names:
            summary = perf.get_agent_summary(
                agent_name=agent_name,
                start_date=start_date,
                end_date=end_date,
            )

            click.echo(f"\n{agent_name}:")
            click.echo(f"  Total Executions: {summary.total_executions}")
            click.echo(f"  Success Rate: {_format_percentage(summary.success_rate)}")
            click.echo(f"  Avg Duration: {_format_duration(summary.average_duration_seconds)}")
            click.echo(f"  Error Rate: {_format_percentage(summary.error_rate)}")

            if summary.total_executions > 0:
                click.echo(f"  Status Distribution:")
                for status, count in summary.status_distribution.items():
                    pct = (count / summary.total_executions) * 100
                    click.echo(f"    {status}: {count} ({pct:.1f}%)")

    except Exception as e:
        click.echo(f"Error retrieving agent performance: {e}", err=True)
        if ctx.obj["verbose"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


# === ROI Command ===

@analytics.command()
@click.option(
    "--days",
    "-d",
    type=int,
    default=30,
    help="Number of days to analyze (default: 30).",
)
@click.option(
    "--trend",
    is_flag=True,
    help="Show trend over time.",
)
@click.pass_context
def roi(
    ctx: click.Context,
    days: int,
    trend: bool,
) -> None:
    """
    Show ROI metrics.

    Displays time saved, cost efficiency, and return on investment
    for autonomous development.

    \b
    Metrics shown:
        - Total time saved
        - Manual hours avoided
        - Autonomous hours
        - Efficiency ratio
        - Cost savings estimate
    """
    calculator = ROICalculator()

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        metrics = calculator.get_roi_summary(
            start_date=start_date,
            end_date=end_date,
        )

        if ctx.obj["output_json"]:
            _print_json({
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": days,
                },
                "metrics": {
                    "total_time_saved_hours": metrics.total_time_saved_hours,
                    "manual_hours_avoided": metrics.manual_hours_avoided,
                    "autonomous_hours": metrics.autonomous_hours,
                    "efficiency_ratio": metrics.efficiency_ratio,
                    "cost_savings_estimate": metrics.cost_savings_estimate,
                },
            })
            return

        # Human-readable output
        click.echo(f"ROI Metrics (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Total Time Saved: {metrics.total_time_saved_hours:.1f}h")
        click.echo(f"Manual Hours Avoided: {metrics.manual_hours_avoided:.1f}h")
        click.echo(f"Autonomous Hours: {metrics.autonomous_hours:.1f}h")
        click.echo(f"Efficiency Ratio: {metrics.efficiency_ratio:.1f}x")
        click.echo(f"Cost Savings Estimate: ${metrics.cost_savings_estimate:.2f}")

        if trend:
            click.echo("\nTrend:")
            trend_data = calculator.get_roi_trend(
                start_date=start_date,
                end_date=end_date,
                bucket_days=max(1, days // 10),
            )

            for data_point in trend_data[:5]:  # Show first 5 data points
                click.echo(
                    f"  {_format_datetime(data_point.date)}: "
                    f"{data_point.time_saved_hours:.1f}h saved, "
                    f"{data_point.efficiency_ratio:.1f}x efficiency"
                )

    except Exception as e:
        click.echo(f"Error retrieving ROI metrics: {e}", err=True)
        if ctx.obj["verbose"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


# === Export Command ===

@analytics.command()
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["json", "markdown", "html"], case_sensitive=False),
    default="json",
    help="Output format (default: json).",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (default: stdout).",
)
@click.option(
    "--days",
    "-d",
    type=int,
    default=30,
    help="Number of days to include (default: 30).",
)
@click.pass_context
def export(
    ctx: click.Context,
    output_format: str,
    output_path: Optional[Path],
    days: int,
) -> None:
    """
    Export analytics report.

    Generates a comprehensive analytics report in the specified format.
    Includes velocity, quality, agent performance, and ROI metrics.

    \b
    Formats:
        - json: Machine-readable JSON
        - markdown: Human-readable Markdown
        - html: Interactive HTML with embedded charts

    \b
    Examples:
        autoflow analytics export --format json --output report.json
        autoflow analytics export --format markdown --output report.md
        autoflow analytics export --format html --output report.html
    """
    try:
        from autoflow.analytics.reports import ReportGenerator

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        generator = ReportGenerator()

        # Generate report
        if output_format == "json":
            report = generator.generate_json_report(
                start_date=start_date,
                end_date=end_date,
            )
            content = json.dumps(report, indent=2, default=str)
        elif output_format == "markdown":
            report = generator.generate_markdown_report(
                start_date=start_date,
                end_date=end_date,
            )
            content = report
        elif output_format == "html":
            report = generator.generate_html_report(
                start_date=start_date,
                end_date=end_date,
            )
            content = report
        else:
            click.echo(f"Unsupported format: {output_format}", err=True)
            ctx.exit(1)

        # Write to file or stdout
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
            if not ctx.obj["output_json"]:
                click.echo(f"Report exported to: {output_path}")
        else:
            click.echo(content)

    except ImportError:
        click.echo(
            "Report generator not available. "
            "This feature will be implemented in a future update.",
            err=True,
        )
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error exporting report: {e}", err=True)
        if ctx.obj["verbose"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


# === Metrics Command ===

@analytics.command()
@click.option(
    "--metric",
    "-m",
    type=str,
    help="Specific metric name to query.",
)
@click.option(
    "--days",
    "-d",
    type=int,
    default=7,
    help="Number of days to analyze (default: 7).",
)
@click.pass_context
def metrics(
    ctx: click.Context,
    metric: Optional[str],
    days: int,
) -> None:
    """
    Show raw metrics.

    Displays collected metrics data. Useful for debugging and
    detailed analysis.

    \b
    Examples:
        autoflow analytics metrics
        autoflow analytics metrics --metric task_duration
    """
    collector = MetricsCollector()

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        if metric:
            # Show specific metric
            summary = collector.get_metric_summary(
                metric_name=metric,
                start_date=start_date,
                end_date=end_date,
            )

            if ctx.obj["output_json"]:
                _print_json({
                    "metric": metric,
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "days": days,
                    },
                    "summary": {
                        "count": summary.count,
                        "mean": summary.mean,
                        "median": summary.median,
                        "min": summary.min,
                        "max": summary.max,
                        "stddev": summary.stddev,
                    },
                })
                return

            click.echo(f"Metric: {metric}")
            click.echo("=" * 60)
            click.echo(f"Count: {summary.count}")
            click.echo(f"Mean: {summary.mean:.2f}")
            click.echo(f"Median: {summary.median:.2f}")
            click.echo(f"Min: {summary.min:.2f}")
            click.echo(f"Max: {summary.max:.2f}")
            click.echo(f"Std Dev: {summary.stddev:.2f}")

        else:
            # List all metrics
            all_metrics = collector.list_metrics(
                start_date=start_date,
                end_date=end_date,
            )

            if ctx.obj["output_json"]:
                _print_json({
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "days": days,
                    },
                    "metrics": all_metrics,
                })
                return

            click.echo(f"Available Metrics (Last {days} days)")
            click.echo("=" * 60)

            if not all_metrics:
                click.echo("No metrics found.")
            else:
                for metric_name in sorted(all_metrics):
                    summary = collector.get_metric_summary(
                        metric_name=metric_name,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    click.echo(f"\n{metric_name}:")
                    click.echo(f"  Count: {summary.count}")
                    click.echo(f"  Mean: {summary.mean:.2f}")
                    click.echo(f"  Range: [{summary.min:.2f}, {summary.max:.2f}]")

    except Exception as e:
        click.echo(f"Error retrieving metrics: {e}", err=True)
        if ctx.obj["verbose"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


if __name__ == "__main__":
    analytics()
