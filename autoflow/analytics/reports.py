"""Report generation and export for analytics.

This module provides comprehensive report generation capabilities for analytics data.
It supports multiple export formats (JSON, Markdown, HTML) and aggregates data from
all analytics modules to create stakeholder-ready reports.

The report generator supports:
- JSON export for programmatic access
- Markdown export for documentation
- HTML export with embedded charts for presentations
- Configurable time ranges and filters
- Aggregated metrics across all analytics dimensions

Usage:
    from autoflow.analytics import ReportGenerator

    generator = ReportGenerator()
    report = generator.generate_report(
        format="json",
        start_time=datetime.now(timezone.utc) - timedelta(days=7),
        end_time=datetime.now(timezone.utc),
    )
    generator.save_report(report, Path("weekly_report.json"))
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from autoflow.analytics.agent_performance import AgentPerformance, AgentComparison
from autoflow.analytics.metrics import MetricsCollector
from autoflow.analytics.quality import QualityTrends, QualityMetrics
from autoflow.analytics.roi import ROICalculator, ROIMetrics
from autoflow.analytics.velocity import VelocityTracker, VelocityMetrics


class ReportFormat(str, Enum):
    """Supported report export formats.

    Attributes:
        JSON: Machine-readable JSON format
        MARKDOWN: Human-readable Markdown format
        HTML: Rich HTML format with embedded charts
    """

    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


@dataclass
class ReportData:
    """Aggregated analytics data for reporting.

    Attributes:
        generated_at: When the report was generated (ISO format string)
        time_range: Start and end timestamps for the report data
        velocity: Velocity metrics including task completion rates
        quality: Quality metrics including test pass rates
        agent_performance: Agent performance comparison data
        roi: ROI metrics including time saved
        summary: High-level summary statistics
    """

    generated_at: str
    time_range: dict[str, str]
    velocity: VelocityMetrics | None = None
    quality: QualityMetrics | None = None
    agent_performance: dict[str, Any] | None = None
    roi: ROIMetrics | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Convert velocity metrics to dict with datetime and enum handling
        velocity_dict = None
        if self.velocity:
            velocity_dict = dataclasses.asdict(self.velocity)
            # Convert datetime fields to ISO format strings
            if velocity_dict.get("period_start"):
                velocity_dict["period_start"] = velocity_dict[
                    "period_start"
                ].isoformat()
            if velocity_dict.get("period_end"):
                velocity_dict["period_end"] = velocity_dict["period_end"].isoformat()
            # Convert enum to string
            if velocity_dict.get("trend"):
                velocity_dict["trend"] = velocity_dict["trend"].value

        return {
            "generated_at": self.generated_at,
            "time_range": self.time_range,
            "velocity": velocity_dict,
            "quality": self.quality.to_dict() if self.quality else None,
            "agent_performance": self.agent_performance,
            "roi": self.roi.to_dict() if self.roi else None,
            "summary": self.summary,
        }


@dataclass
class ReportConfig:
    """Configuration for report generation.

    Attributes:
        format: Output format (json, markdown, html)
        start_time: Start of time window for report data
        end_time: End of time window for report data
        include_charts: Whether to include charts in HTML reports
        hourly_rate: Hourly rate for ROI calculations (USD)
    """

    format: ReportFormat = ReportFormat.JSON
    start_time: datetime | None = None
    end_time: datetime | None = None
    include_charts: bool = True
    hourly_rate: float = 100.0


class ReportGenerator:
    """Generate analytics reports in multiple formats.

    This class aggregates data from all analytics modules and generates
    comprehensive reports in JSON, Markdown, or HTML format. Reports can
    be saved to files or returned as strings for further processing.

    The generator integrates with:
    - VelocityTracker for task completion metrics
    - QualityTrends for quality metrics
    - AgentPerformance for agent comparison
    - ROICalculator for ROI calculations
    - MetricsCollector for raw metrics data

    Example:
        generator = ReportGenerator()
        report = generator.generate_json_report()
        generator.save_report(report, Path("analytics_report.json"))

        # Markdown report
        md_report = generator.generate_markdown_report()
        generator.save_report(md_report, Path("report.md"))

        # HTML report
        html_report = generator.generate_html_report()
        generator.save_report(html_report, Path("report.html"))
    """

    # Default paths
    DEFAULT_REPORTS_DIR = Path(".autoflow/reports")

    def __init__(
        self,
        root_dir: Path | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        """Initialize the report generator.

        Args:
            root_dir: Root directory of the project. Defaults to current directory.
            reports_dir: Directory to save reports. Defaults to DEFAULT_REPORTS_DIR.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if reports_dir is None:
            reports_dir = self.DEFAULT_REPORTS_DIR

        self.root_dir = Path(root_dir)
        self.reports_dir = Path(reports_dir)

        # Ensure reports directory exists
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Initialize metrics collector first
        self._metrics = MetricsCollector(root_dir=self.root_dir)

        # Initialize analytics modules
        self._velocity = VelocityTracker(metrics_collector=self._metrics)
        self._quality = QualityTrends(root_dir=self.root_dir)
        self._agent_perf = AgentPerformance(root_dir=self.root_dir)
        self._roi = ROICalculator(root_dir=self.root_dir)

    def generate_report(
        self,
        config: ReportConfig | None = None,
    ) -> str:
        """Generate a report in the specified format.

        This is the main entry point for report generation. It aggregates
        data from all analytics modules and formats it according to the
        specified configuration.

        Args:
            config: Report configuration. If None, uses defaults (JSON, all time).

        Returns:
            Report content as a string (JSON, Markdown, or HTML)

        Raises:
            ValueError: If report format is not supported
            IOError: If unable to read analytics data
        """
        if config is None:
            config = ReportConfig()

        # Set default time range (last 7 days)
        if config.start_time is None:
            config.start_time = datetime.now(UTC) - timedelta(days=7)
        if config.end_time is None:
            config.end_time = datetime.now(UTC)

        # Collect analytics data
        report_data = self._collect_data(config.start_time, config.end_time)

        # Generate report in requested format
        if config.format == ReportFormat.JSON:
            return self._generate_json(report_data)
        elif config.format == ReportFormat.MARKDOWN:
            return self._generate_markdown(report_data)
        elif config.format == ReportFormat.HTML:
            return self._generate_html(
                report_data, include_charts=config.include_charts
            )
        else:
            raise ValueError(f"Unsupported report format: {config.format}")

    def generate_json_report(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """Generate a JSON format report.

        Args:
            start_time: Start of time window. Defaults to 7 days ago.
            end_time: End of time window. Defaults to now.

        Returns:
            JSON string containing report data
        """
        config = ReportConfig(
            format=ReportFormat.JSON, start_time=start_time, end_time=end_time
        )
        return self.generate_report(config)

    def generate_markdown_report(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """Generate a Markdown format report.

        Args:
            start_time: Start of time window. Defaults to 7 days ago.
            end_time: End of time window. Defaults to now.

        Returns:
            Markdown string containing formatted report
        """
        config = ReportConfig(
            format=ReportFormat.MARKDOWN, start_time=start_time, end_time=end_time
        )
        return self.generate_report(config)

    def generate_html_report(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        include_charts: bool = True,
    ) -> str:
        """Generate an HTML format report with embedded charts.

        Args:
            start_time: Start of time window. Defaults to 7 days ago.
            end_time: End of time window. Defaults to now.
            include_charts: Whether to include Chart.js visualizations

        Returns:
            HTML string containing formatted report with optional charts
        """
        config = ReportConfig(
            format=ReportFormat.HTML,
            start_time=start_time,
            end_time=end_time,
            include_charts=include_charts,
        )
        return self.generate_report(config)

    def save_report(
        self,
        content: str,
        output_path: Path,
    ) -> None:
        """Save report content to a file.

        Args:
            content: Report content (JSON, Markdown, or HTML)
            output_path: Path to save the report file

        Raises:
            IOError: If unable to write to the output file
        """
        output_path = Path(output_path)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            output_path.write_text(content, encoding="utf-8")
        except OSError as e:
            raise IOError(f"Failed to write report to {output_path}: {e}") from e

    def _collect_data(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> ReportData:
        """Collect analytics data from all modules.

        Args:
            start_time: Start of time window
            end_time: End of time window

        Returns:
            ReportData with aggregated analytics
        """
        # Calculate period days for modules that use period_days instead of datetime ranges
        time_delta = end_time - start_time
        period_days = max(1, int(time_delta.total_seconds() / 86400))

        # Collect metrics from all modules
        velocity = self._velocity.get_velocity_metrics(period_days=period_days)
        quality = self._quality.get_quality_metrics(period_days=period_days)
        roi = self._roi.get_roi_summary(start_time=start_time, end_time=end_time)

        # Get agent performance comparison
        agent_comparison = self._agent_perf.compare_agents(
            start_time=start_time, end_time=end_time
        )

        # Build summary statistics
        summary = self._build_summary(velocity, quality, roi, agent_comparison)

        return ReportData(
            generated_at=datetime.now(UTC).isoformat(),
            time_range={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            velocity=velocity,
            quality=quality,
            agent_performance=agent_comparison.to_dict() if agent_comparison else None,
            roi=roi,
            summary=summary,
        )

    def _build_summary(
        self,
        velocity: VelocityMetrics | None,
        quality: QualityMetrics | None,
        roi: ROIMetrics | None,
        agent_comparison: AgentComparison | None,
    ) -> dict[str, Any]:
        """Build high-level summary statistics.

        Args:
            velocity: Velocity metrics
            quality: Quality metrics
            roi: ROI metrics
            agent_comparison: Agent performance comparison

        Returns:
            Dictionary of summary statistics
        """
        summary: dict[str, Any] = {}

        if velocity:
            summary["total_tasks"] = velocity.tasks_completed
            summary["avg_cycle_time_minutes"] = (
                velocity.avg_cycle_time / 60 if velocity.avg_cycle_time else 0
            )
            summary["completion_rate"] = velocity.completion_rate
            summary["tasks_per_day"] = velocity.throughput

        if quality:
            summary["test_pass_rate"] = quality.test_pass_rate
            summary["quality_score"] = quality.quality_score
            summary["review_approval_rate"] = quality.review_approval_rate
            summary["total_tests"] = quality.test_total

        if roi:
            summary["total_time_saved_hours"] = roi.total_time_saved_hours
            summary["cost_saved_usd"] = roi.cost_savings_estimate_usd
            summary["roi_percentage"] = roi.roi_percentage
            # Calculate average times in minutes
            if roi.total_tasks > 0:
                summary["avg_manual_time_minutes"] = (
                    roi.total_manual_time_estimate_seconds / 60
                ) / roi.total_tasks
                summary["avg_autonomous_time_minutes"] = (
                    roi.total_autoflow_time_seconds / 60
                ) / roi.total_tasks

        if agent_comparison:
            summary["best_performing_agent"] = agent_comparison.best_success_rate
            summary["total_executions"] = len(agent_comparison.agents)
            summary["most_used_agent"] = agent_comparison.most_used
            summary["fastest_agent"] = agent_comparison.fastest_avg

        return summary

    def _generate_json(self, data: ReportData) -> str:
        """Generate JSON format report.

        Args:
            data: Report data to serialize

        Returns:
            JSON string
        """
        report_dict = {
            "report": "analytics",
            "version": "1.0",
            "data": data.to_dict(),
        }

        return json.dumps(report_dict, indent=2) + "\n"

    def _generate_markdown(self, data: ReportData) -> str:
        """Generate Markdown format report.

        Args:
            data: Report data to format

        Returns:
            Markdown string
        """
        lines = [
            "# Analytics Report",
            "",
            f"**Generated:** {data.generated_at}",
            f"**Period:** {data.time_range['start']} to {data.time_range['end']}",
            "",
            "---",
            "",
            "## Summary",
            "",
        ]

        # Add summary statistics
        if data.summary:
            for key, value in data.summary.items():
                if isinstance(value, float):
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value:.2f}")
                elif value is not None:
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
            lines.append("")

        # Add velocity section
        if data.velocity:
            lines.extend(
                [
                    "## Velocity Metrics",
                    "",
                    f"- **Total Tasks:** {data.velocity.tasks_completed}",
                    f"- **Average Cycle Time:** {data.velocity.avg_cycle_time / 60:.2f} minutes",
                    f"- **Completion Rate:** {data.velocity.completion_rate:.1f}%",
                    f"- **Tasks Per Day:** {data.velocity.throughput:.2f}",
                    "",
                ]
            )

        # Add quality section
        if data.quality:
            lines.extend(
                [
                    "## Quality Metrics",
                    "",
                    f"- **Test Pass Rate:** {data.quality.test_pass_rate:.1f}%",
                    f"- **Quality Score:** {data.quality.quality_score:.1f}",
                    f"- **Review Approval Rate:** {data.quality.review_approval_rate:.1f}%",
                    f"- **Total Tests Run:** {data.quality.test_total}",
                    "",
                ]
            )

        # Add ROI section
        if data.roi:
            lines.extend(
                [
                    "## ROI Metrics",
                    "",
                    f"- **Time Saved:** {data.roi.total_time_saved_hours:.2f} hours",
                    f"- **Cost Saved:** ${data.roi.cost_savings_estimate_usd:.2f}"
                    if data.roi.cost_savings_estimate_usd
                    else "- **Cost Saved:** N/A",
                    f"- **ROI:** {data.roi.roi_percentage:.1f}%",
                    "",
                ]
            )

            # Add manual vs autonomous comparison if available
            if data.roi.total_tasks > 0:
                avg_manual = (
                    data.roi.total_manual_time_estimate_seconds / 60
                ) / data.roi.total_tasks
                avg_autonomous = (
                    data.roi.total_autoflow_time_seconds / 60
                ) / data.roi.total_tasks
                lines.append(
                    f"- **Manual vs Autonomous:** {avg_manual:.0f}m vs {avg_autonomous:.0f}m"
                )
                lines.append("")

        # Add agent performance section
        if data.agent_performance:
            lines.extend(
                [
                    "## Agent Performance",
                    "",
                    f"- **Best Success Rate:** {data.agent_performance.get('best_success_rate', 'N/A')}",
                    f"- **Fastest Agent:** {data.agent_performance.get('fastest_avg', 'N/A')}",
                    f"- **Most Used:** {data.agent_performance.get('most_used', 'N/A')}",
                    f"- **Total Agents:** {len(data.agent_performance.get('agents', []))}",
                    "",
                ]
            )

            if data.agent_performance.get("comparison_data"):
                lines.append("### Agent Comparison")
                lines.append("")
                lines.append("| Agent | Success Rate | Avg Duration | Executions |")
                lines.append("|-------|--------------|--------------|------------|")

                for agent, comp in data.agent_performance["comparison_data"].items():
                    success_rate = comp.get("success_rate", 0)
                    avg_duration = comp.get("avg_duration_seconds", 0)
                    executions = comp.get("total_executions", 0)
                    lines.append(
                        f"| {agent} | {success_rate:.1f}% | {avg_duration:.1f}s | {executions} |"
                    )
                lines.append("")

        lines.extend(
            [
                "---",
                "",
                "*Generated by Autoflow Analytics*",
            ]
        )

        return "\n".join(lines)

    def _generate_html(self, data: ReportData, include_charts: bool = True) -> str:
        """Generate HTML format report with optional embedded charts.

        Args:
            data: Report data to format
            include_charts: Whether to include Chart.js visualizations

        Returns:
            HTML string
        """
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "    <title>Autoflow Analytics Report</title>",
            "    <style>",
            "        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }",
            "        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
            "        h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }",
            "        h2 { color: #555; margin-top: 30px; }",
            "        .metadata { color: #666; font-size: 14px; margin-bottom: 20px; }",
            "        .metric { background: #f9f9f9; padding: 15px; margin: 10px 0; border-left: 4px solid #4CAF50; border-radius: 4px; }",
            "        .metric-label { font-weight: bold; color: #333; }",
            "        .metric-value { font-size: 24px; color: #4CAF50; margin-top: 5px; }",
            "        .section { margin: 30px 0; }",
            "        table { width: 100%; border-collapse: collapse; margin: 20px 0; }",
            "        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }",
            "        th { background: #f5f5f5; font-weight: 600; }",
            "        .footer { margin-top: 40px; text-align: center; color: #999; font-size: 12px; }",
            "    </style>",
        ]

        if include_charts:
            html_parts.extend(
                [
                    "    <script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js'></script>",
                ]
            )

        html_parts.extend(
            [
                "</head>",
                "<body>",
                "    <div class='container'>",
                "        <h1>📊 Autoflow Analytics Report</h1>",
                f"        <div class='metadata'>Generated: {data.generated_at}<br>Period: {data.time_range['start']} to {data.time_range['end']}</div>",
                "",
                "        <div class='section'>",
                "            <h2>Summary</h2>",
            ]
        )

        # Summary metrics
        if data.summary:
            for key, value in data.summary.items():
                if isinstance(value, float):
                    display_value = f"{value:.2f}"
                else:
                    display_value = str(value) if value is not None else "N/A"

                html_parts.extend(
                    [
                        f"            <div class='metric'>",
                        f"                <div class='metric-label'>{key.replace('_', ' ').title()}</div>",
                        f"                <div class='metric-value'>{display_value}</div>",
                        "            </div>",
                    ]
                )

        html_parts.append("        </div>")

        # Velocity section with chart
        if data.velocity:
            if include_charts:
                html_parts.extend(
                    [
                        "        <div class='section'>",
                        "            <h2>Velocity Metrics</h2>",
                        "            <canvas id='velocityChart' style='max-height: 300px;'></canvas>",
                        f"            <div class='metric'><div class='metric-label'>Total Tasks</div><div class='metric-value'>{data.velocity.tasks_completed}</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Avg Cycle Time</div><div class='metric-value'>{data.velocity.avg_cycle_time / 60:.2f} min</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Completion Rate</div><div class='metric-value'>{data.velocity.completion_rate:.1f}%</div></div>",
                        "        </div>",
                    ]
                )
            else:
                html_parts.extend(
                    [
                        "        <div class='section'>",
                        "            <h2>Velocity Metrics</h2>",
                        f"            <div class='metric'><div class='metric-label'>Total Tasks</div><div class='metric-value'>{data.velocity.tasks_completed}</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Avg Cycle Time</div><div class='metric-value'>{data.velocity.avg_cycle_time / 60:.2f} min</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Completion Rate</div><div class='metric-value'>{data.velocity.completion_rate:.1f}%</div></div>",
                        "        </div>",
                    ]
                )

        # Quality section with chart
        if data.quality:
            if include_charts:
                html_parts.extend(
                    [
                        "        <div class='section'>",
                        "            <h2>Quality Metrics</h2>",
                        "            <canvas id='qualityChart' style='max-height: 300px;'></canvas>",
                        f"            <div class='metric'><div class='metric-label'>Test Pass Rate</div><div class='metric-value'>{data.quality.test_pass_rate:.1f}%</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Quality Score</div><div class='metric-value'>{data.quality.quality_score:.1f}</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Review Approval Rate</div><div class='metric-value'>{data.quality.review_approval_rate:.1f}%</div></div>",
                        "        </div>",
                    ]
                )
            else:
                html_parts.extend(
                    [
                        "        <div class='section'>",
                        "            <h2>Quality Metrics</h2>",
                        f"            <div class='metric'><div class='metric-label'>Test Pass Rate</div><div class='metric-value'>{data.quality.test_pass_rate:.1f}%</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Quality Score</div><div class='metric-value'>{data.quality.quality_score:.1f}</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Review Approval Rate</div><div class='metric-value'>{data.quality.review_approval_rate:.1f}%</div></div>",
                        "        </div>",
                    ]
                )

        # ROI section with chart
        if data.roi:
            cost_saved = (
                f"${data.roi.cost_savings_estimate_usd:.2f}"
                if data.roi.cost_savings_estimate_usd
                else "N/A"
            )
            if include_charts:
                html_parts.extend(
                    [
                        "        <div class='section'>",
                        "            <h2>ROI Metrics</h2>",
                        "            <canvas id='roiChart' style='max-height: 300px;'></canvas>",
                        f"            <div class='metric'><div class='metric-label'>Time Saved</div><div class='metric-value'>{data.roi.total_time_saved_hours:.2f} hours</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Cost Saved</div><div class='metric-value'>{cost_saved}</div></div>",
                        f"            <div class='metric'><div class='metric-label'>ROI</div><div class='metric-value'>{data.roi.roi_percentage:.1f}%</div></div>",
                        "        </div>",
                    ]
                )
            else:
                html_parts.extend(
                    [
                        "        <div class='section'>",
                        "            <h2>ROI Metrics</h2>",
                        f"            <div class='metric'><div class='metric-label'>Time Saved</div><div class='metric-value'>{data.roi.total_time_saved_hours:.2f} hours</div></div>",
                        f"            <div class='metric'><div class='metric-label'>Cost Saved</div><div class='metric-value'>{cost_saved}</div></div>",
                        f"            <div class='metric'><div class='metric-label'>ROI</div><div class='metric-value'>{data.roi.roi_percentage:.1f}%</div></div>",
                        "        </div>",
                    ]
                )

        # Agent performance section
        if data.agent_performance and data.agent_performance.get("comparison_data"):
            html_parts.extend(
                [
                    "        <div class='section'>",
                    "            <h2>Agent Performance Comparison</h2>",
                    "            <table>",
                    "                <thead><tr><th>Agent</th><th>Success Rate</th><th>Avg Duration</th><th>Executions</th></tr></thead>",
                    "                <tbody>",
                ]
            )

            for agent, comp in data.agent_performance["comparison_data"].items():
                success_rate = comp.get("success_rate", 0)
                avg_duration = comp.get("avg_duration_seconds", 0)
                executions = comp.get("total_executions", 0)
                html_parts.append(
                    f"                    <tr><td>{agent}</td><td>{success_rate:.1f}%</td><td>{avg_duration:.1f}s</td><td>{executions}</td></tr>"
                )

            html_parts.extend(
                [
                    "                </tbody>",
                    "            </table>",
                    "        </div>",
                ]
            )

        html_parts.extend(
            [
                "        <div class='footer'>",
                "            Generated by Autoflow Analytics",
                "        </div>",
                "    </div>",
            ]
        )

        # Add JavaScript for chart rendering
        if include_charts:
            # Prepare chart data
            chart_data = self._prepare_chart_data(data)

            html_parts.extend(
                [
                    "    <script>",
                    "        // Chart.js configuration",
                    "        const chartDefaults = {",
                    "            responsive: true,",
                    "            maintainAspectRatio: true,",
                    "            plugins: {",
                    "                legend: {",
                    "                    position: 'bottom'",
                    "                }",
                    "            }",
                    "        };",
                ]
            )

            # Velocity chart
            if data.velocity and chart_data.get("velocity"):
                html_parts.extend(
                    [
                        "",
                        "        // Velocity Chart",
                        f"        const velocityCtx = document.getElementById('velocityChart');",
                        f"        if (velocityCtx) {{",
                        f"            new Chart(velocityCtx, {{",
                        f"                type: 'bar',",
                        f"                data: {chart_data['velocity']},",
                        f"                options: {{...chartDefaults, plugins: {{ title: {{ display: true, text: 'Task Completion & Performance' }} }} }}",
                        f"            }});",
                        f"        }}",
                    ]
                )

            # Quality chart
            if data.quality and chart_data.get("quality"):
                html_parts.extend(
                    [
                        "",
                        "        // Quality Chart",
                        f"        const qualityCtx = document.getElementById('qualityChart');",
                        f"        if (qualityCtx) {{",
                        f"            new Chart(qualityCtx, {{",
                        f"                type: 'line',",
                        f"                data: {chart_data['quality']},",
                        f"                options: {{...chartDefaults, plugins: {{ title: {{ display: true, text: 'Quality Metrics Over Time' }} }} }}",
                        f"            }});",
                        f"        }}",
                    ]
                )

            # ROI chart
            if data.roi and chart_data.get("roi"):
                html_parts.extend(
                    [
                        "",
                        "        // ROI Chart",
                        f"        const roiCtx = document.getElementById('roiChart');",
                        f"        if (roiCtx) {{",
                        f"            new Chart(roiCtx, {{",
                        f"                type: 'doughnut',",
                        f"                data: {chart_data['roi']},",
                        f"                options: {{...chartDefaults, plugins: {{ title: {{ display: true, text: 'Time Distribution' }} }} }}",
                        f"            }});",
                        f"        }}",
                    ]
                )

            html_parts.append("    </script>")

        html_parts.extend(
            [
                "</body>",
                "</html>",
            ]
        )

        return "\n".join(html_parts)

    def _prepare_chart_data(self, data: ReportData) -> dict[str, str]:
        """Prepare JavaScript chart data objects for HTML reports.

        Args:
            data: Report data to visualize

        Returns:
            Dictionary with JavaScript data objects for charts
        """
        import json as json_lib

        chart_data: dict[str, str] = {}

        # Velocity chart data
        if data.velocity:
            velocity_data = {
                "labels": [
                    "Tasks Completed",
                    "Avg Cycle Time (min)",
                    "Completion Rate (%)",
                ],
                "datasets": [
                    {
                        "label": "Velocity Metrics",
                        "data": [
                            data.velocity.tasks_completed,
                            round(data.velocity.avg_cycle_time / 60, 2)
                            if data.velocity.avg_cycle_time
                            else 0,
                            round(data.velocity.completion_rate, 1),
                        ],
                        "backgroundColor": ["#4CAF50", "#2196F3", "#FF9800"],
                        "borderColor": ["#45a049", "#1976D2", "#F57C00"],
                        "borderWidth": 1,
                    },
                ],
            }
            chart_data["velocity"] = json_lib.dumps(velocity_data)

        # Quality chart data
        if data.quality:
            quality_data = {
                "labels": ["Test Pass Rate", "Quality Score", "Review Approval Rate"],
                "datasets": [
                    {
                        "label": "Quality Metrics",
                        "data": [
                            round(data.quality.test_pass_rate, 1),
                            round(data.quality.quality_score, 1),
                            round(data.quality.review_approval_rate, 1),
                        ],
                        "fill": False,
                        "borderColor": "#9C27B0",
                        "backgroundColor": "#9C27B0",
                        "tension": 0.1,
                    },
                ],
            }
            chart_data["quality"] = json_lib.dumps(quality_data)

        # ROI chart data
        if data.roi:
            roi_data = {
                "labels": [
                    "Manual Time (hrs)",
                    "Autoflow Time (hrs)",
                    "Time Saved (hrs)",
                ],
                "datasets": [
                    {
                        "label": "Time Distribution",
                        "data": [
                            round(
                                data.roi.total_manual_time_estimate_seconds / 3600, 2
                            ),
                            round(data.roi.total_autoflow_time_seconds / 3600, 2),
                            round(data.roi.total_time_saved_hours, 2),
                        ],
                        "backgroundColor": ["#f44336", "#4CAF50", "#2196F3"],
                        "hoverOffset": 4,
                    },
                ],
            }
            chart_data["roi"] = json_lib.dumps(roi_data)

        return chart_data
