"""
Autoflow FastAPI Application

Main FastAPI application with middleware, lifecycle events, and route registration.
Provides the web API layer for enterprise SSO and RBAC functionality.

Usage:
    from autoflow.api.main import app, get_app

    # Run directly with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # Or get a configured app instance
    app = get_app(title="My Autoflow Instance")
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logger = logging.getLogger(__name__)


# Default API configuration
DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8000
DEFAULT_API_TITLE = "Autoflow API"
DEFAULT_API_DESCRIPTION = """Autoflow - Autonomous AI Development System

Enterprise-grade API with SSO integration and role-based access control.
"""
DEFAULT_API_VERSION = "0.1.0"
DEFAULT_DOCS_URL = "/docs"
DEFAULT_REDOC_URL = "/redoc"


def get_app(
    title: str = DEFAULT_API_TITLE,
    description: str = DEFAULT_API_DESCRIPTION,
    version: str = DEFAULT_API_VERSION,
    docs_url: Optional[str] = DEFAULT_DOCS_URL,
    redoc_url: Optional[str] = DEFAULT_REDOC_URL,
) -> FastAPI:
    """
    Create and configure a FastAPI application instance.

    This function creates a new FastAPI application with:
    - CORS middleware for cross-origin requests
    - Lifespan events for database connection management
    - OpenAPI documentation configuration
    - Health check endpoint
    - API versioning prefix (/api/v1)

    Args:
        title: API title (shown in OpenAPI docs)
        description: API description (shown in OpenAPI docs)
        version: API version string
        docs_url: Path to Swagger UI docs (None to disable)
        redoc_url: Path to ReDoc docs (None to disable)

    Returns:
        Configured FastAPI application instance

    Example:
        >>> app = get_app(title="My API", version="2.0.0")
        >>> @app.get("/")
        ... def root():
        ...     return {"message": "Hello"}
    """
    # Create FastAPI application
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
        contact={
            "name": "Autoflow Team",
            "url": "https://github.com/autoflow/autoflow",
        },
    )

    # Configure CORS middleware
    # In production, configure specific origins instead of wildcard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register startup event handler
    @app.on_event("startup")
    async def startup_event() -> None:
        """
        Initialize application on startup.

        - Initialize database connections
        - Load configuration
        - Initialize authentication components
        """
        logger.info("Starting Autoflow API...")

        try:
            # Initialize database (optional - may fail if dependencies not installed)
            try:
                from autoflow.db import init_db

                init_db()
                logger.info("Database initialized")
            except ImportError as e:
                logger.warning(f"Database initialization skipped: {e}")
                logger.info("API running without database support")

            # TODO: Initialize auth components
            # from autoflow.auth.defaults import seed_roles_and_permissions
            # seed_roles_and_permissions()

            logger.info("Autoflow API startup complete")
        except Exception as e:
            logger.error(f"Error during startup: {e}", exc_info=True)
            raise

    # Register shutdown event handler
    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """
        Cleanup on application shutdown.

        - Close database connections
        - Flush any pending audit logs
        """
        logger.info("Shutting down Autoflow API...")

        try:
            # Close database connections (optional)
            try:
                from autoflow.db import close_db

                close_db()
                logger.info("Database connections closed")
            except ImportError:
                logger.info("Database cleanup skipped (not available)")

            logger.info("Autoflow API shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

    # Health check endpoint (no authentication required)
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint.

        Returns API status for load balancers and monitoring systems.
        Does not require authentication.

        Returns:
            Dictionary with status information
        """
        return {"status": "healthy", "service": "autoflow-api"}

    # API info endpoint
    @app.get("/api/v1/info")
    async def api_info() -> dict[str, str]:
        """
        API information endpoint.

        Returns basic API information.
        Does not require authentication.

        Returns:
            Dictionary with API metadata
        """
        return {
            "name": title,
            "version": version,
            "description": "Autoflow - Autonomous AI Development System",
        }

    # Register routers
    from autoflow.api.routes import auth, users, specs

    app.include_router(
        auth.router, prefix="/api/v1/auth", tags=["Authentication"]
    )
    app.include_router(
        users.router, prefix="/api/v1/users", tags=["User Management"]
    )
    app.include_router(
        specs.router, prefix="/api/v1/specs", tags=["Specifications"]
    )
    # TODO: Register additional routers
    # from autoflow.api.routes import tasks
    # app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])

    return app


# Global application instance
# This is the default instance used when running the module directly
app = get_app()


if __name__ == "__main__":
    # Run the application directly for development
    import uvicorn

    uvicorn.run(
        "autoflow.api.main:app",
        host=DEFAULT_API_HOST,
        port=DEFAULT_API_PORT,
        reload=True,  # Enable auto-reload for development
        log_level="info",
    )
