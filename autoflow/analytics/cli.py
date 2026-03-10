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
from datetime import UTC, datetime, timedelta
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
        metrics = tracker.get_velocity_metrics(period_days=days)

        if ctx.obj["output_json"]:
            _print_json({
                "period": {
                    "start": metrics.period_start.isoformat(),
                    "end": metrics.period_end.isoformat(),
                    "days": days,
                },
                "metrics": {
                    "tasks_completed": metrics.tasks_completed,
                    "tasks_started": metrics.tasks_started,
                    "avg_cycle_time_seconds": metrics.avg_cycle_time,
                    "avg_lead_time_seconds": metrics.avg_lead_time,
                    "throughput_per_day": metrics.throughput,
                    "completion_rate": metrics.completion_rate,
                    "trend": metrics.trend.value,
                },
            })
            return

        # Human-readable output
        click.echo(f"Velocity Metrics (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Tasks Completed: {metrics.tasks_completed}")
        click.echo(f"Tasks Started: {metrics.tasks_started}")
        click.echo(f"Avg Cycle Time: {_format_duration(metrics.avg_cycle_time)}")
        click.echo(f"Avg Lead Time: {_format_duration(metrics.avg_lead_time)}")
        click.echo(f"Throughput: {metrics.throughput:.2f} tasks/day")
        click.echo(f"Completion Rate: {_format_percentage(metrics.completion_rate)}")
        click.echo(f"Trend: {metrics.trend.value}")

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
        metrics = trends.get_quality_metrics(period_days=days)

        if ctx.obj["output_json"]:
            _print_json({
                "period": {
                    "start": metrics.period_start,
                    "end": metrics.period_end,
                    "days": days,
                },
                "metrics": {
                    "test_pass_rate": metrics.test_pass_rate,
                    "test_total": metrics.test_total,
                    "review_approval_rate": metrics.review_approval_rate,
                    "review_first_try_rate": metrics.review_first_try_rate,
                    "review_total": metrics.review_total,
                    "defect_density": metrics.defect_density,
                    "quality_score": metrics.quality_score,
                    "trend": metrics.trend.value,
                },
            })
            return

        # Human-readable output
        click.echo(f"Quality Trends (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Test Pass Rate: {_format_percentage(metrics.test_pass_rate)}")
        click.echo(f"Test Total: {metrics.test_total}")
        click.echo(f"Review Approval Rate: {_format_percentage(metrics.review_approval_rate)}")
        click.echo(f"Review First-Try Rate: {_format_percentage(metrics.review_first_try_rate)}")
        click.echo(f"Review Total: {metrics.review_total}")
        click.echo(f"Quality Score: {metrics.quality_score:.1f}/100")
        click.echo(f"Trend: {metrics.trend.value}")

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
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)

        if compare:
            # Compare specific agents
            agent_names = list(compare)
        else:
            # Show all agents
            agent_names = perf.get_agent_names()

        if ctx.obj["output_json"]:
            comparison = perf.compare_agents(
                agent_names=agent_names,
                start_time=start_time,
                end_time=end_time,
            )

            _print_json({
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
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
                start_time=start_time,
                end_time=end_time,
            )

            click.echo(f"\n{agent_name}:")
            click.echo(f"  Total Executions: {summary.total_executions}")
            click.echo(f"  Successful: {summary.successful_executions}")
            click.echo(f"  Failed: {summary.failed_executions}")
            click.echo(f"  Success Rate: {_format_percentage(summary.success_rate)}")
            click.echo(f"  Avg Duration: {_format_duration(summary.avg_duration_seconds)}")
            click.echo(f"  Min Duration: {_format_duration(summary.min_duration_seconds)}")
            click.echo(f"  Max Duration: {_format_duration(summary.max_duration_seconds)}")

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
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)

        metrics = calculator.get_roi_summary(
            start_time=start_time,
            end_time=end_time,
        )

        if ctx.obj["output_json"]:
            _print_json({
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": days,
                },
                "metrics": {
                    "total_tasks": metrics.total_tasks,
                    "total_time_saved_hours": metrics.total_time_saved_hours,
                    "manual_hours_estimate": metrics.total_manual_time_estimate_seconds / 3600,
                    "autoflow_hours": metrics.total_autoflow_time_seconds / 3600,
                    "avg_efficiency_ratio": metrics.avg_efficiency_ratio,
                    "roi_percentage": metrics.roi_percentage,
                },
            })
            return

        # Human-readable output
        click.echo(f"ROI Metrics (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Total Tasks: {metrics.total_tasks}")
        click.echo(f"Total Time Saved: {metrics.total_time_saved_hours:.1f}h")
        click.echo(f"Manual Hours Estimate: {metrics.total_manual_time_estimate_seconds / 3600:.1f}h")
        click.echo(f"Autoflow Hours: {metrics.total_autoflow_time_seconds / 3600:.1f}h")
        click.echo(f"Avg Efficiency Ratio: {metrics.avg_efficiency_ratio:.1f}x")
        click.echo(f"ROI Percentage: {metrics.roi_percentage:.1f}%")
        if metrics.cost_savings_estimate_usd is not None:
            click.echo(f"Cost Savings Estimate: ${metrics.cost_savings_estimate_usd:.2f}")

        if trend:
            click.echo("\nTrend:")
            trend_data = calculator.get_roi_trend(
                start_time=start_time,
                end_time=end_time,
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
        from datetime import UTC

        from autoflow.analytics.reports import ReportGenerator

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        generator = ReportGenerator()

        # Generate report
        if output_format == "json":
            content = generator.generate_json_report(
                start_time=start_date,
                end_time=end_date,
            )
        elif output_format == "markdown":
            content = generator.generate_markdown_report(
                start_time=start_date,
                end_time=end_date,
            )
        elif output_format == "html":
            content = generator.generate_html_report(
                start_time=start_date,
                end_time=end_date,
            )
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
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)

        if metric:
            # Show specific metric
            summary = collector.get_metric_summary(
                metric_name=metric,
                start_time=start_time,
                end_time=end_time,
            )

            if ctx.obj["output_json"]:
                _print_json({
                    "metric": metric,
                    "period": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
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
            all_metrics = collector.get_metric_names()

            if ctx.obj["output_json"]:
                _print_json({
                    "period": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
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
                        start_time=start_time,
                        end_time=end_time,
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
