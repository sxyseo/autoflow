"""Unit Tests for Autoflow Analytics Reports

Tests the ReportGenerator class and related models (ReportData, ReportConfig)
for report generation in multiple formats (JSON, Markdown, HTML).

These tests use temporary directories and mock analytics modules to avoid
affecting real analytics data and to ensure isolated testing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.analytics.reports import (
    ReportConfig,
    ReportData,
    ReportFormat,
    ReportGenerator,
)
from autoflow.analytics.velocity import VelocityMetrics, VelocityTrend
from autoflow.analytics.quality import QualityMetrics, QualityTrend
from autoflow.analytics.roi import ROIMetrics
from autoflow.analytics.agent_performance import AgentComparison


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_reports_dir(tmp_path: Path) -> Path:
    """Create a temporary reports directory."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


@pytest.fixture
def sample_velocity_metrics() -> VelocityMetrics:
    """Return sample velocity metrics for testing."""
    return VelocityMetrics(
        period_start=datetime.now(UTC) - timedelta(days=7),
        period_end=datetime.now(UTC),
        tasks_completed=42,
        tasks_started=50,
        completion_rate=85.5,
        avg_cycle_time=1800.0,  # 30 minutes in seconds
        avg_lead_time=2100.0,  # 35 minutes in seconds
        throughput=6.0,
        trend=VelocityTrend.IMPROVING,
        forecasted_completion=45,
    )


@pytest.fixture
def sample_quality_metrics() -> QualityMetrics:
    """Return sample quality metrics for testing."""
    return QualityMetrics(
        period_start=(datetime.now(UTC) - timedelta(days=7)).isoformat(),
        period_end=datetime.now(UTC).isoformat(),
        test_pass_rate=94.7,
        test_total=150,
        review_approval_rate=92.1,
        review_first_try_rate=88.0,
        review_total=45,
        defect_density=0.5,
        trend=QualityTrend.STABLE,
        quality_score=88.3,
    )


@pytest.fixture
def sample_roi_metrics() -> ROIMetrics:
    """Return sample ROI metrics for testing."""
    return ROIMetrics(
        period_start=(datetime.now(UTC) - timedelta(days=7)).isoformat(),
        period_end=datetime.now(UTC).isoformat(),
        total_tasks=42,
        total_manual_time_estimate_seconds=151200,  # 42 hours
        total_autoflow_time_seconds=37800,  # 10.5 hours
        total_time_saved_seconds=113400,  # 31.5 hours
        total_time_saved_hours=31.5,
        avg_efficiency_ratio=4.0,
        median_efficiency_ratio=3.8,
        roi_percentage=300.0,
        cost_savings_estimate_usd=3150.0,
        tasks_by_complexity={"low": 10, "medium": 20, "high": 12},
        time_saved_by_complexity={"low": 3600.0, "medium": 54000.0, "high": 55800.0},
    )


@pytest.fixture
def sample_agent_comparison() -> AgentComparison:
    """Return sample agent comparison data for testing."""
    return AgentComparison(
        agents=["claude-code", "codex"],
        comparison_data={
            "claude-code": {
                "success_rate": 95.0,
                "avg_duration_seconds": 450.0,
                "total_executions": 25,
            },
            "codex": {
                "success_rate": 88.5,
                "avg_duration_seconds": 520.0,
                "total_executions": 17,
            },
        },
        best_success_rate="claude-code",
        fastest_avg="claude-code",
        most_used="claude-code",
    )


@pytest.fixture
def mock_analytics_modules(
    sample_velocity_metrics: VelocityMetrics,
    sample_quality_metrics: QualityMetrics,
    sample_roi_metrics: ROIMetrics,
    sample_agent_comparison: dict,
) -> dict[str, Any]:
    """Create mock analytics modules for testing."""
    # Use actual dataclass instances
    return {
        "velocity": sample_velocity_metrics,
        "quality": sample_quality_metrics,
        "roi": sample_roi_metrics,
        "agent_comparison": sample_agent_comparison,
    }


# ============================================================================
# ReportFormat Enum Tests
# ============================================================================


class TestReportFormat:
    """Tests for ReportFormat enum."""

    def test_report_format_values(self) -> None:
        """Test ReportFormat enum values."""
        assert ReportFormat.JSON == "json"
        assert ReportFormat.MARKDOWN == "markdown"
        assert ReportFormat.HTML == "html"

    def test_report_format_is_string(self) -> None:
        """Test that ReportFormat values are strings."""
        assert isinstance(ReportFormat.JSON.value, str)

    def test_report_format_from_string(self) -> None:
        """Test creating ReportFormat from string."""
        format_ = ReportFormat("markdown")
        assert format_ == ReportFormat.MARKDOWN


# ============================================================================
# ReportData Model Tests
# ============================================================================


class TestReportData:
    """Tests for ReportData model."""

    def test_report_data_init_minimal(self) -> None:
        """Test ReportData initialization with minimal fields."""
        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
        )

        assert data.generated_at == "2024-01-01T00:00:00Z"
        assert data.time_range == {"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"}
        assert data.velocity is None
        assert data.quality is None
        assert data.agent_performance is None
        assert data.roi is None
        assert data.summary == {}

    def test_report_data_init_full(
        self,
        sample_velocity_metrics: VelocityMetrics,
        sample_quality_metrics: QualityMetrics,
        sample_roi_metrics: ROIMetrics,
        sample_agent_comparison: dict,
    ) -> None:
        """Test ReportData initialization with all fields."""
        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            velocity=sample_velocity_metrics,
            quality=sample_quality_metrics,
            agent_performance=sample_agent_comparison,
            roi=sample_roi_metrics,
            summary={"total_tasks": 42},
        )

        assert data.generated_at == "2024-01-01T00:00:00Z"
        assert data.velocity is not None
        assert data.quality is not None
        assert data.agent_performance is not None
        assert data.roi is not None
        assert data.summary == {"total_tasks": 42}

    def test_report_data_to_dict_minimal(self) -> None:
        """Test ReportData.to_dict() with minimal data."""
        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
        )

        result = data.to_dict()

        assert result["generated_at"] == "2024-01-01T00:00:00Z"
        assert result["time_range"] == {"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"}
        assert result["velocity"] is None
        assert result["quality"] is None
        assert result["agent_performance"] is None
        assert result["roi"] is None
        assert result["summary"] == {}

    def test_report_data_to_dict_with_velocity(
        self,
        sample_velocity_metrics: VelocityMetrics,
    ) -> None:
        """Test ReportData.to_dict() with velocity metrics."""
        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            velocity=sample_velocity_metrics,
        )

        result = data.to_dict()

        assert result["velocity"] is not None
        assert result["velocity"]["tasks_completed"] == 42
        assert result["velocity"]["avg_cycle_time"] == 1800.0
        assert result["velocity"]["completion_rate"] == 85.5
        assert result["velocity"]["trend"] == "improving"
        # Check datetime fields are converted to ISO format
        assert "period_start" in result["velocity"]
        assert "period_end" in result["velocity"]

    def test_report_data_to_dict_with_quality(
        self,
        sample_quality_metrics: QualityMetrics,
    ) -> None:
        """Test ReportData.to_dict() with quality metrics."""
        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            quality=sample_quality_metrics,
        )

        result = data.to_dict()

        assert result["quality"] is not None
        assert result["quality"]["test_total"] == 150
        assert result["quality"]["test_pass_rate"] == 94.7
        assert result["quality"]["quality_score"] == 88.3


# ============================================================================
# ReportConfig Model Tests
# ============================================================================


class TestReportConfig:
    """Tests for ReportConfig model."""

    def test_report_config_defaults(self) -> None:
        """Test ReportConfig initialization with defaults."""
        config = ReportConfig()

        assert config.format == ReportFormat.JSON
        assert config.start_time is None
        assert config.end_time is None
        assert config.include_charts is True
        assert config.hourly_rate == 100.0

    def test_report_config_full(self) -> None:
        """Test ReportConfig initialization with all fields."""
        start = datetime.now(UTC) - timedelta(days=7)
        end = datetime.now(UTC)

        config = ReportConfig(
            format=ReportFormat.HTML,
            start_time=start,
            end_time=end,
            include_charts=False,
            hourly_rate=150.0,
        )

        assert config.format == ReportFormat.HTML
        assert config.start_time == start
        assert config.end_time == end
        assert config.include_charts is False
        assert config.hourly_rate == 150.0


# ============================================================================
# ReportGenerator Init Tests
# ============================================================================


class TestReportGeneratorInit:
    """Tests for ReportGenerator initialization."""

    def test_init_with_defaults(self, tmp_path: Path) -> None:
        """Test ReportGenerator initialization with defaults."""
        with patch.object(ReportGenerator, "DEFAULT_REPORTS_DIR", tmp_path / "reports"):
            generator = ReportGenerator()

            assert generator.root_dir == Path.cwd()
            assert generator.reports_dir == tmp_path / "reports"
            assert generator._metrics is not None
            assert generator._velocity is not None
            assert generator._quality is not None
            assert generator._agent_perf is not None
            assert generator._roi is not None

    def test_init_with_custom_dirs(self, tmp_path: Path) -> None:
        """Test ReportGenerator initialization with custom directories."""
        root_dir = tmp_path / "project"
        reports_dir = tmp_path / "custom_reports"
        root_dir.mkdir(parents=True, exist_ok=True)

        generator = ReportGenerator(root_dir=root_dir, reports_dir=reports_dir)

        assert generator.root_dir == root_dir
        assert generator.reports_dir == reports_dir

    def test_init_creates_reports_dir(self, tmp_path: Path) -> None:
        """Test ReportGenerator initialization creates reports directory."""
        reports_dir = tmp_path / "new_reports"

        generator = ReportGenerator(reports_dir=reports_dir)

        assert reports_dir.exists()
        assert generator.reports_dir == reports_dir

    def test_init_with_string_paths(self, tmp_path: Path) -> None:
        """Test ReportGenerator initialization with string paths."""
        root_dir = str(tmp_path / "project")
        reports_dir = str(tmp_path / "reports")
        Path(root_dir).mkdir(parents=True, exist_ok=True)

        generator = ReportGenerator(root_dir=root_dir, reports_dir=reports_dir)

        assert generator.root_dir == Path(root_dir)
        assert generator.reports_dir == Path(reports_dir)


# ============================================================================
# ReportGenerator Report Generation Tests
# ============================================================================


class TestReportGeneratorGenerateReport:
    """Tests for ReportGenerator.generate_report() method."""

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_report_json_default_config(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_report() with default JSON config."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        result = generator.generate_report()

        assert result is not None
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["report"] == "analytics"
        assert parsed["version"] == "1.0"
        assert "data" in parsed

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_report_markdown_format(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_report() with Markdown format."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        config = ReportConfig(format=ReportFormat.MARKDOWN)
        result = generator.generate_report(config)

        assert result is not None
        assert "# Analytics Report" in result
        assert "## Summary" in result
        assert "## Velocity Metrics" in result

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_report_html_format(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_report() with HTML format."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        config = ReportConfig(format=ReportFormat.HTML)
        result = generator.generate_report(config)

        assert result is not None
        assert "<!DOCTYPE html>" in result
        assert "<title>Autoflow Analytics Report</title>" in result
        assert "Chart.js" in result

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_report_custom_time_range(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_report() with custom time range."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        start = datetime.now(UTC) - timedelta(days=14)
        end = datetime.now(UTC)

        config = ReportConfig(
            format=ReportFormat.JSON,
            start_time=start,
            end_time=end,
        )

        result = generator.generate_report(config)

        assert result is not None
        parsed = json.loads(result)
        # Verify time range is reflected in report
        assert "data" in parsed
        assert "time_range" in parsed["data"]

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_report_unsupported_format(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_report() raises ValueError for unsupported format."""
        # Setup mocks
        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        # Create invalid config
        config = MagicMock()
        config.format = "invalid_format"
        config.start_time = datetime.now(UTC) - timedelta(days=7)
        config.end_time = datetime.now(UTC)

        with pytest.raises(ValueError, match="Unsupported report format"):
            generator.generate_report(config)


# ============================================================================
# ReportGenerator Convenience Methods Tests
# ============================================================================


class TestReportGeneratorConvenienceMethods:
    """Tests for ReportGenerator convenience methods."""

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_json_report(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_json_report() convenience method."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        result = generator.generate_json_report()

        assert result is not None
        parsed = json.loads(result)
        assert parsed["report"] == "analytics"

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_markdown_report(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_markdown_report() convenience method."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        result = generator.generate_markdown_report()

        assert result is not None
        assert "# Analytics Report" in result

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_html_report_with_charts(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_html_report() with charts enabled."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        result = generator.generate_html_report(include_charts=True)

        assert result is not None
        assert "Chart.js" in result
        assert "<canvas" in result

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_generate_html_report_without_charts(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        mock_analytics_modules: dict,
        tmp_path: Path,
    ) -> None:
        """Test generate_html_report() with charts disabled."""
        # Setup mocks
        mock_velocity_instance = MagicMock()
        mock_velocity_instance.get_velocity_metrics.return_value = mock_analytics_modules["velocity"]
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality_instance.get_quality_metrics.return_value = mock_analytics_modules["quality"]
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent_instance.compare_agents.return_value = mock_analytics_modules["agent_comparison"]
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi_instance.get_roi_summary.return_value = mock_analytics_modules["roi"]
        mock_roi.return_value = mock_roi_instance

        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        result = generator.generate_html_report(include_charts=False)

        assert result is not None
        assert "Chart.js" not in result
        # Should still have HTML structure
        assert "<!DOCTYPE html>" in result


# ============================================================================
# ReportGenerator Save Report Tests
# ============================================================================


class TestReportGeneratorSaveReport:
    """Tests for ReportGenerator.save_report() method."""

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_save_report_creates_file(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test save_report() creates file."""
        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        mock_velocity_instance = MagicMock()
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi.return_value = mock_roi_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        content = '{"test": "data"}'
        output_path = tmp_path / "output" / "test_report.json"

        generator.save_report(content, output_path)

        assert output_path.exists()
        assert output_path.read_text() == content

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_save_report_creates_parent_dirs(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test save_report() creates parent directories."""
        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        mock_velocity_instance = MagicMock()
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi.return_value = mock_roi_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        content = "# Test Report"
        output_path = tmp_path / "deep" / "nested" / "dir" / "report.md"

        generator.save_report(content, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_save_report_with_path_object(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test save_report() with Path object."""
        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        mock_velocity_instance = MagicMock()
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi.return_value = mock_roi_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        content = "<html></html>"
        output_path = Path(tmp_path / "report.html")

        generator.save_report(content, output_path)

        assert output_path.exists()

    @patch("autoflow.analytics.reports.VelocityTracker")
    @patch("autoflow.analytics.reports.QualityTrends")
    @patch("autoflow.analytics.reports.AgentPerformance")
    @patch("autoflow.analytics.reports.ROICalculator")
    @patch("autoflow.analytics.reports.MetricsCollector")
    def test_save_report_unicode_content(
        self,
        mock_collector: MagicMock,
        mock_roi: MagicMock,
        mock_agent: MagicMock,
        mock_quality: MagicMock,
        mock_velocity: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test save_report() handles unicode content."""
        mock_collector_instance = MagicMock()
        mock_collector.return_value = mock_collector_instance

        mock_velocity_instance = MagicMock()
        mock_velocity.return_value = mock_velocity_instance

        mock_quality_instance = MagicMock()
        mock_quality.return_value = mock_quality_instance

        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        mock_roi_instance = MagicMock()
        mock_roi.return_value = mock_roi_instance

        generator = ReportGenerator(reports_dir=tmp_path / "reports")
        content = "Hello 世界 🌍"
        output_path = tmp_path / "unicode_report.txt"

        generator.save_report(content, output_path)

        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == content


# ============================================================================
# ReportGenerator Internal Methods Tests
# ============================================================================


class TestReportGeneratorInternalMethods:
    """Tests for ReportGenerator internal methods."""

    def test_generate_json_output(self, tmp_path: Path) -> None:
        """Test _generate_json() produces valid JSON."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            summary={"total_tasks": 42},
        )

        result = generator._generate_json(data)

        assert result is not None
        parsed = json.loads(result)
        assert parsed["report"] == "analytics"
        assert parsed["version"] == "1.0"
        assert parsed["data"]["summary"]["total_tasks"] == 42

    def test_generate_markdown_output(self, tmp_path: Path) -> None:
        """Test _generate_markdown() produces valid Markdown."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            summary={"total_tasks": 42, "completion_rate": 85.5},
        )

        result = generator._generate_markdown(data)

        assert "# Analytics Report" in result
        assert "**Generated:** 2024-01-01T00:00:00Z" in result
        assert "## Summary" in result
        assert "- **Total Tasks:** 42" in result
        assert "- **Completion Rate:** 85.50" in result
        assert "*Generated by Autoflow Analytics*" in result

    def test_generate_html_output(self, tmp_path: Path) -> None:
        """Test _generate_html() produces valid HTML."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            summary={"total_tasks": 42},
        )

        result = generator._generate_html(data, include_charts=False)

        assert "<!DOCTYPE html>" in result
        assert "<title>Autoflow Analytics Report</title>" in result
        assert "Autoflow Analytics Report" in result
        assert "Total Tasks" in result
        assert "42" in result

    def test_prepare_chart_data(
        self,
        tmp_path: Path,
        sample_velocity_metrics: VelocityMetrics,
        sample_quality_metrics: QualityMetrics,
        sample_roi_metrics: ROIMetrics,
    ) -> None:
        """Test _prepare_chart_data() generates chart JavaScript objects."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            velocity=sample_velocity_metrics,
            quality=sample_quality_metrics,
            roi=sample_roi_metrics,
        )

        chart_data = generator._prepare_chart_data(data)

        assert "velocity" in chart_data
        assert "quality" in chart_data
        assert "roi" in chart_data

        # Verify chart data is valid JSON
        velocity_chart = json.loads(chart_data["velocity"])
        assert velocity_chart["labels"] == ["Tasks Completed", "Avg Cycle Time (min)", "Completion Rate (%)"]
        assert len(velocity_chart["datasets"]) == 1

        quality_chart = json.loads(chart_data["quality"])
        assert quality_chart["labels"] == ["Test Pass Rate", "Quality Score", "Review Approval Rate"]

        roi_chart = json.loads(chart_data["roi"])
        assert "Manual Time (hrs)" in roi_chart["labels"]


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestReportGeneratorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_report_data_to_dict_none_metrics(self) -> None:
        """Test ReportData.to_dict() handles None metrics gracefully."""
        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            velocity=None,
            quality=None,
            roi=None,
            agent_performance=None,
        )

        result = data.to_dict()

        assert result["velocity"] is None
        assert result["quality"] is None
        assert result["roi"] is None
        assert result["agent_performance"] is None

    def test_generate_markdown_empty_summary(self, tmp_path: Path) -> None:
        """Test _generate_markdown() with empty summary."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            summary={},
        )

        result = generator._generate_markdown(data)

        # Should still have headers
        assert "# Analytics Report" in result
        assert "## Summary" in result

    def test_prepare_chart_data_none_metrics(self, tmp_path: Path) -> None:
        """Test _prepare_chart_data() with None metrics."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            velocity=None,
            quality=None,
            roi=None,
        )

        chart_data = generator._prepare_chart_data(data)

        assert chart_data == {}

    def test_generate_html_with_none_agent_performance(self, tmp_path: Path) -> None:
        """Test _generate_html() with None agent performance."""
        generator = ReportGenerator(reports_dir=tmp_path / "reports")

        data = ReportData(
            generated_at="2024-01-01T00:00:00Z",
            time_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-08T00:00:00Z"},
            agent_performance=None,
        )

        result = generator._generate_html(data, include_charts=False)

        # Should not crash
        assert "<!DOCTYPE html>" in result
        # Should not have agent performance section
        assert "Agent Performance Comparison" not in result
