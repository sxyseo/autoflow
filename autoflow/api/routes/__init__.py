"""
Autoflow API Routes

FastAPI route handlers for the Autoflow API.
Includes authentication, user management, specifications, and task endpoints.

Usage:
    from autoflow.api.routes import auth, users, specs, tasks

    # Register routes with FastAPI app
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
"""

from __future__ import annotations

from autoflow.api.routes import auth

__all__ = [
    "auth",
]
