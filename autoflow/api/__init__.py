"""
Autoflow Web API Module

Provides FastAPI application and REST API endpoints for accessing
Autoflow functionality through a web interface.

Usage:
    from autoflow.api.main import app, get_app
    import uvicorn

    # Run the application
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # Or get a configured app instance
    app = get_app()
"""

from __future__ import annotations

from autoflow.api.main import app, get_app

__all__ = ["app", "get_app"]
