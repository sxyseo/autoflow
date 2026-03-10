"""
Autoflow Database Module

Provides database session management, connection handling, and utilities
for working with SQLAlchemy models.

Usage:
    from autoflow.db.session import get_db, init_db

    # Get a database session (for use with FastAPI dependencies)
    db = get_db()

    # Initialize database (create tables)
    init_db()
"""

from __future__ import annotations

from autoflow.db.session import SessionManager, get_db, init_db

__all__ = ["SessionManager", "get_db", "init_db"]
