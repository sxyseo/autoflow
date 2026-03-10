"""
Autoflow Web - Dashboard API and Monitoring

This module provides the web dashboard interface:
- FastAPI REST endpoints for state queries
- WebSocket endpoints for real-time updates
- File monitor for detecting state changes
- Static file serving for dashboard UI
"""

from autoflow.web.app import app

__all__ = [
    "app",
]
