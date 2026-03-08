"""Autoflow Analytics Module

Provides comprehensive analytics and performance tracking for the Autoflow system.
This module tracks velocity metrics, quality trends, agent performance, and ROI
measurements to enable data-driven optimization of autonomous development.

Core Components:
    MetricsCollector: Base metrics collection and aggregation
    VelocityTracker: Task completion rates and cycle times
    QualityTrends: Test pass rates and review outcomes
    AgentPerformance: Backend effectiveness comparison
    ROICalculator: Time saved vs manual effort

Usage:
    from autoflow.analytics import MetricsCollector, QualityTrends, AgentPerformance, ROICalculator

    collector = MetricsCollector()
    collector.record_metric("task_duration", 45.2, metadata={"task_id": "build-123"})
    summary = collector.get_metric_summary("task_duration")
    print(f"Average duration: {summary.mean:.2f}s")

    trends = QualityTrends()
    metrics = trends.get_quality_metrics()
    print(f"Test pass rate: {metrics.test_pass_rate:.1f}%")

    perf = AgentPerformance()
    perf.record_execution("claude_code", "success", 45.2)
    summary = perf.get_agent_summary("claude_code")
    print(f"Success rate: {summary.success_rate:.1f}%")

    roi = ROICalculator()
    roi.record_task_completion("build-123", 1800, 7200, TaskComplexity.MEDIUM)
    metrics = roi.get_roi_summary()
    print(f"Time saved: {metrics.total_time_saved_hours:.1f}h")
"""

from autoflow.analytics.agent_performance import (
    AgentComparison,
    AgentExecutionRecord,
    AgentExecutionStatus,
    AgentPerformance,
    AgentPerformanceSummary,
)
from autoflow.analytics.metrics import (
    MetricReading,
    MetricSummary,
    MetricType,
    MetricsCollector,
)
from autoflow.analytics.quality import (
    QualityMetrics,
    QualitySummary,
    QualityTrend,
    QualityTrends,
    ReviewOutcome,
    ReviewRecord,
    TestResult,
    TestStatus,
)
from autoflow.analytics.velocity import (
    VelocityTracker,
    VelocityMetrics,
    TaskRecord as VelocityTaskRecord,
)
from autoflow.analytics.roi import (
    ROICalculator,
    ROIMetrics,
    ROIRecord,
    ROITrend,
    TaskComplexity,
)
from autoflow.analytics.reports import (
    ReportFormat,
    ReportData,
    ReportGenerator,
    ReportConfig,
)

__all__ = [
    "MetricsCollector",
    "MetricReading",
    "MetricSummary",
    "MetricType",
    "VelocityTracker",
    "VelocityMetrics",
    "VelocityTaskRecord",
    "QualityTrends",
    "QualityMetrics",
    "QualitySummary",
    "QualityTrend",
    "TestResult",
    "TestStatus",
    "ReviewRecord",
    "ReviewOutcome",
    "AgentPerformance",
    "AgentExecutionRecord",
    "AgentPerformanceSummary",
    "AgentComparison",
    "AgentExecutionStatus",
    "ROICalculator",
    "ROIMetrics",
    "ROIRecord",
    "ROITrend",
    "TaskComplexity",
    "ReportGenerator",
    "ReportFormat",
    "ReportData",
    "ReportConfig",
]
