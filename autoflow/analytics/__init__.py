"""Autoflow Analytics Module

Provides comprehensive analytics and performance tracking for the Autoflow system.
This module tracks velocity metrics, quality trends, agent performance, and ROI
measurements to enable data-driven optimization of autonomous development.

Core Components:
    MetricsCollector: Base metrics collection and aggregation
    VelocityTracker: Task completion rates and cycle times
    QualityTrends: Test pass rates and review outcomes
    (AgentPerformance): Backend effectiveness comparison (future)
    (ROICalculator): Time saved vs manual effort (future)

Usage:
    from autoflow.analytics import MetricsCollector, QualityTrends

    collector = MetricsCollector()
    collector.record_metric("task_duration", 45.2, metadata={"task_id": "build-123"})
    summary = collector.get_metric_summary("task_duration")
    print(f"Average duration: {summary.mean:.2f}s")

    trends = QualityTrends()
    metrics = trends.get_quality_metrics()
    print(f"Test pass rate: {metrics.test_pass_rate:.1f}%")
"""

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

__all__ = [
    "MetricsCollector",
    "MetricReading",
    "MetricSummary",
    "MetricType",
    "QualityTrends",
    "QualityMetrics",
    "QualitySummary",
    "QualityTrend",
    "TestResult",
    "TestStatus",
    "ReviewRecord",
    "ReviewOutcome",
]
