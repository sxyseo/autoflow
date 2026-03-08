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

from typing import Any

from fastapi import FastAPI

# Create FastAPI application
app = FastAPI(
    title="Autoflow Analytics API",
    description="Performance analytics and metrics for autonomous development",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint - API information.

    Returns:
        Dictionary with API metadata and available endpoints
    """
    return {
        "name": "Autoflow Analytics API",
        "version": "0.1.0",
        "status": "operational",
        "endpoints": {
            "api": "/api",
            "docs": "/api/docs",
            "health": "/health",
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
