"""
Autoflow Web Application - FastAPI App

This module provides the FastAPI application with REST and WebSocket endpoints
for the web dashboard. Exposes state data from StateManager for monitoring.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Autoflow Dashboard",
    description="Real-time monitoring dashboard for autonomous development workflows",
    version="0.1.0",
)


@app.get("/")
async def root():
    """Root endpoint - basic health check."""
    return {"status": "ok", "message": "Autoflow Dashboard API"}


@app.get("/api/status")
async def status():
    """API status endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
