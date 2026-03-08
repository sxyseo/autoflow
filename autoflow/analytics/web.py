"""FastAPI web server for analytics dashboard.

This module provides a lightweight web server for visualizing analytics data.
It exposes REST API endpoints for accessing metrics, velocity, quality trends,
agent performance, and ROI measurements.

The web server uses FastAPI for async request handling and uvicorn for serving.
Static assets and HTML templates are served for the dashboard UI.

Usage:
    from autoflow.analytics.web import app

    # Run with uvicorn directly
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # Or run from command line
    autoflow analytics serve
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from autoflow.analytics.agent_performance import AgentPerformance
from autoflow.analytics.metrics import MetricsCollector
from autoflow.analytics.quality import QualityTrends
from autoflow.analytics.roi import ROICalculator
from autoflow.analytics.velocity import VelocityTracker

# Create FastAPI application
app = FastAPI(
    title="Autoflow Analytics API",
    description="Performance analytics and metrics for autonomous development",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Get the directory containing this module
_current_dir = Path(__file__).parent

# Mount static files directory
_static_dir = _current_dir / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Initialize analytics collectors
_metrics_collector: MetricsCollector | None = None
_velocity_tracker: VelocityTracker | None = None
_quality_tracker: QualityTrends | None = None
_agent_performance: AgentPerformance | None = None
_roi_calculator: ROICalculator | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the metrics collector instance.

    Returns:
        MetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_velocity_tracker() -> VelocityTracker:
    """Get or create the velocity tracker instance.

    Returns:
        VelocityTracker instance
    """
    global _velocity_tracker
    if _velocity_tracker is None:
        _velocity_tracker = VelocityTracker(
            metrics_collector=get_metrics_collector()
        )
    return _velocity_tracker


def get_quality_tracker() -> QualityTrends:
    """Get or create the quality trends tracker instance.

    Returns:
        QualityTrends instance
    """
    global _quality_tracker
    if _quality_tracker is None:
        _quality_tracker = QualityTrends()
    return _quality_tracker


def get_agent_performance() -> AgentPerformance:
    """Get or create the agent performance tracker instance.

    Returns:
        AgentPerformance instance
    """
    global _agent_performance
    if _agent_performance is None:
        _agent_performance = AgentPerformance()
    return _agent_performance


def get_roi_calculator() -> ROICalculator:
    """Get or create the ROI calculator instance.

    Returns:
        ROICalculator instance
    """
    global _roi_calculator
    if _roi_calculator is None:
        _roi_calculator = ROICalculator()
    return _roi_calculator


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    """Serve the analytics dashboard HTML.

    Returns:
        HTML content for the dashboard
    """
    template_path = _current_dir / "templates" / "dashboard.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Autoflow Analytics</title>
    </head>
    <body>
        <h1>Analytics Dashboard</h1>
        <p>Dashboard template not found. Please ensure the template file exists.</p>
        <p><a href="/api/docs">View API Documentation</a></p>
    </body>
    </html>
    """


@app.get("/api")
async def api_info() -> dict[str, Any]:
    """API information endpoint.

    Returns:
        Dictionary with API details and available resources
    """
    return {
        "name": "Autoflow Analytics API",
        "version": "0.1.0",
        "status": "operational",
        "endpoints": {
            "api": "/api",
            "docs": "/api/docs",
            "health": "/health",
            "dashboard": "/",
        },
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Dictionary with health status
    """
    return {"status": "healthy"}


@app.get("/api")
async def api_info() -> dict[str, Any]:
    """API information endpoint.

    Returns:
        Dictionary with API details and available resources
    """
    return {
        "version": "0.1.0",
        "resources": {
            "metrics": "/api/metrics",
            "velocity": "/api/velocity",
            "quality": "/api/quality",
            "agents": "/api/agents",
            "roi": "/api/roi",
        },
    }


# Metrics endpoints
@app.get("/api/metrics")
async def get_metrics(
    limit: int = Query(100, description="Maximum number of readings to return", ge=1, le=1000),
    metric_name: str | None = Query(None, description="Filter by metric name"),
) -> dict[str, Any]:
    """Get metrics data.

    Args:
        limit: Maximum number of readings to return
        metric_name: Optional metric name to filter by

    Returns:
        Dictionary with metrics data
    """
    try:
        collector = get_metrics_collector()

        # Get metric names
        metric_names = collector.get_metric_names()

        # Get readings
        readings = collector.query_metrics(
            metric_name=metric_name,
            limit=limit,
        )

        return {
            "metric_names": metric_names,
            "total_metrics": len(metric_names),
            "readings": [reading.to_dict() for reading in readings],
            "readings_count": len(readings),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/metrics/{metric_name}")
async def get_metric_details(
    metric_name: str,
    limit: int = Query(100, description="Maximum number of readings to return", ge=1, le=1000),
) -> dict[str, Any]:
    """Get details for a specific metric.

    Args:
        metric_name: Name of the metric
        limit: Maximum number of readings to return

    Returns:
        Dictionary with metric details
    """
    try:
        collector = get_metrics_collector()

        # Check if metric exists
        if metric_name not in collector.get_metric_names():
            raise HTTPException(
                status_code=404,
                detail=f"Metric not found: {metric_name}"
            )

        # Get readings
        readings = collector.query_metrics(
            metric_name=metric_name,
            limit=limit,
        )

        return {
            "metric_name": metric_name,
            "readings": [reading.to_dict() for reading in readings],
            "readings_count": len(readings),
            "total_count": collector.get_metric_count(metric_name),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/metrics/{metric_name}/summary")
async def get_metric_summary(
    metric_name: str,
) -> dict[str, Any]:
    """Get summary statistics for a specific metric.

    Args:
        metric_name: Name of the metric

    Returns:
        Dictionary with metric summary
    """
    try:
        collector = get_metrics_collector()

        # Get summary
        summary = collector.get_metric_summary(metric_name)

        return {
            "metric_name": summary.metric_name,
            "count": summary.count,
            "min": summary.min,
            "max": summary.max,
            "mean": summary.mean,
            "sum": summary.sum,
            "percentile_50": summary.percentile_50,
            "percentile_95": summary.percentile_95,
            "percentile_99": summary.percentile_99,
            "start_time": summary.start_time,
            "end_time": summary.end_time,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Velocity endpoints
@app.get("/api/velocity")
async def get_velocity_metrics(
    period_days: int = Query(7, description="Number of days to analyze", ge=1, le=365),
) -> dict[str, Any]:
    """Get velocity metrics.

    Args:
        period_days: Number of days to analyze

    Returns:
        Dictionary with velocity metrics
    """
    try:
        tracker = get_velocity_tracker()
        metrics = tracker.get_velocity_metrics(period_days=period_days)

        return {
            "period_start": metrics.period_start.isoformat(),
            "period_end": metrics.period_end.isoformat(),
            "tasks_completed": metrics.tasks_completed,
            "tasks_started": metrics.tasks_started,
            "completion_rate": metrics.completion_rate,
            "avg_cycle_time_seconds": metrics.avg_cycle_time,
            "avg_lead_time_seconds": metrics.avg_lead_time,
            "throughput": metrics.throughput,
            "trend": metrics.trend.value,
            "forecasted_completion": metrics.forecasted_completion,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/velocity/cycle-time")
async def get_cycle_time_distribution(
    period_days: int = Query(7, description="Number of days to analyze", ge=1, le=365),
    task_type: str | None = Query(None, description="Filter by task type"),
) -> dict[str, Any]:
    """Get cycle time distribution.

    Args:
        period_days: Number of days to analyze
        task_type: Optional task type filter

    Returns:
        Dictionary with cycle time distribution
    """
    try:
        tracker = get_velocity_tracker()
        distribution = tracker.get_cycle_time_distribution(
            task_type=task_type,
            period_days=period_days,
        )

        if distribution is None:
            return {
                "message": "No completed tasks found for the given criteria",
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "percentile_85": None,
                "percentile_95": None,
                "std_dev": None,
            }

        return {
            "min": distribution.min,
            "max": distribution.max,
            "mean": distribution.mean,
            "median": distribution.median,
            "percentile_85": distribution.percentile_85,
            "percentile_95": distribution.percentile_95,
            "std_dev": distribution.std_dev,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Quality endpoints
@app.get("/api/quality")
async def get_quality_metrics(
    period_days: int = Query(7, description="Number of days to analyze", ge=1, le=365),
) -> dict[str, Any]:
    """Get quality metrics.

    Args:
        period_days: Number of days to analyze

    Returns:
        Dictionary with quality metrics
    """
    try:
        tracker = get_quality_tracker()
        metrics = tracker.get_quality_metrics(period_days=period_days)

        return metrics.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/quality/summary")
async def get_quality_summary() -> dict[str, Any]:
    """Get comprehensive quality summary.

    Returns:
        Dictionary with quality summary
    """
    try:
        tracker = get_quality_tracker()
        summary = tracker.get_summary()

        return {
            "total_tests": summary.total_tests,
            "total_reviews": summary.total_reviews,
            "avg_test_pass_rate": summary.avg_test_pass_rate,
            "avg_review_approval_rate": summary.avg_review_approval_rate,
            "avg_first_try_rate": summary.avg_first_try_rate,
            "total_defects": summary.total_defects,
            "trend": summary.trend.value,
            "quality_score": summary.quality_score,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Agent performance endpoints
@app.get("/api/agents")
async def get_agents(
    limit: int = Query(10, description="Maximum number of executions to return", ge=1, le=100),
) -> dict[str, Any]:
    """Get agent performance data.

    Args:
        limit: Maximum number of recent executions to return

    Returns:
        Dictionary with agent performance data
    """
    try:
        perf = get_agent_performance()

        # Get all agent names
        agent_names = perf.get_agent_names()

        # Get recent executions
        recent_executions = perf.get_recent_executions(limit=limit)

        return {
            "agent_names": agent_names,
            "total_agents": len(agent_names),
            "recent_executions": [
                execution.to_dict() for execution in recent_executions
            ],
            "executions_count": len(recent_executions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/agents/{agent_name}")
async def get_agent_summary(
    agent_name: str,
) -> dict[str, Any]:
    """Get performance summary for a specific agent.

    Args:
        agent_name: Name of the agent

    Returns:
        Dictionary with agent performance summary
    """
    try:
        perf = get_agent_performance()
        summary = perf.get_agent_summary(agent_name)

        return summary.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/agents/compare")
async def compare_agents(
    agents: str = Query(..., description="Comma-separated list of agent names to compare"),
) -> dict[str, Any]:
    """Compare performance across multiple agents.

    Args:
        agents: Comma-separated list of agent names

    Returns:
        Dictionary with agent comparison
    """
    try:
        perf = get_agent_performance()
        agent_list = [a.strip() for a in agents.split(",")]

        comparison = perf.compare_agents(agent_names=agent_list)

        return comparison.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ROI endpoints
@app.get("/api/roi")
async def get_roi_metrics(
    period_days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    hourly_rate_usd: float | None = Query(None, description="Hourly rate for cost calculation", ge=0),
) -> dict[str, Any]:
    """Get ROI metrics.

    Args:
        period_days: Number of days to analyze
        hourly_rate_usd: Optional hourly rate for cost savings calculation

    Returns:
        Dictionary with ROI metrics
    """
    try:
        from datetime import timedelta

        calculator = get_roi_calculator()

        # Calculate time range
        end_time = datetime.now()
        start_time = end_time - timedelta(days=period_days)

        # Get ROI summary
        metrics = calculator.get_roi_summary(
            start_time=start_time,
            end_time=end_time,
            hourly_rate_usd=hourly_rate_usd,
        )

        return metrics.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/roi/trend")
async def get_roi_trend(
    metric_name: str = Query("roi_percentage", description="Metric to analyze"),
    period_hours: int = Query(168, description="Time period in hours", ge=1, le=8760),
) -> dict[str, Any]:
    """Get ROI trend analysis.

    Args:
        metric_name: Name of the metric to analyze
        period_hours: Time period for comparison

    Returns:
        Dictionary with ROI trend
    """
    try:
        calculator = get_roi_calculator()
        trend = calculator.get_roi_trend(
            metric_name=metric_name,
            period_hours=period_hours,
        )

        if trend is None:
            return {
                "message": "Insufficient data for trend analysis",
                "metric_name": metric_name,
                "current_value": None,
                "previous_value": None,
                "change_rate": None,
                "trend_direction": None,
                "confidence": None,
            }

        return {
            "metric_name": trend.metric_name,
            "current_value": trend.current_value,
            "previous_value": trend.previous_value,
            "change_rate": trend.change_rate,
            "trend_direction": trend.trend_direction,
            "confidence": trend.confidence,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the analytics web server.

    This is a convenience function for starting the server programmatically.
    For production use, run with uvicorn directly.

    Args:
        host: Host address to bind to. Defaults to "0.0.0.0".
        port: Port to listen on. Defaults to 8000.

    Example:
        from autoflow.analytics.web import run_server

        run_server(host="127.0.0.1", port=8080)
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)
