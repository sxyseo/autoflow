"""
Autoflow Database Session Management

Provides SQLAlchemy session management with connection pooling,
configuration support, and FastAPI dependency injection.

Usage:
    from autoflow.db.session import get_db, init_db

    # Use with FastAPI dependency injection
    @app.get("/users")
    def list_users(db: Session = Depends(get_db)):
        users = db.query(User).all()
        return users

    # Initialize database (create tables)
    init_db()
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

# Default database configuration
DEFAULT_DATABASE_URL = "sqlite:///./autoflow.db"
ENV_DATABASE_URL = "AUTOFLOW_DATABASE_URL"
ENV_DATABASE_ECHO = "AUTOFLOW_DATABASE_ECHO"


class SessionManager:
    """
    Database session manager with connection pooling.

    Manages SQLAlchemy engine and session factory for database connections.
    Supports configuration via environment variables or explicit parameters.

    Attributes:
        engine: SQLAlchemy engine instance
        SessionLocal: SQLAlchemy session factory

    Example:
        >>> manager = SessionManager(database_url="postgresql://...")
        >>> session = manager.get_session()
        >>> users = session.query(User).all()
        >>> session.close()
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        echo: bool = False,
        connect_args: Optional[dict] = None,
    ) -> None:
        """
        Initialize the session manager.

        Args:
            database_url: Database connection URL. If None, checks AUTOFLOW_DATABASE_URL
                         environment variable, then defaults to SQLite.
            echo: If True, log all SQL statements to stdout (useful for debugging).
            connect_args: Additional arguments to pass to engine.connect()

        Raises:
            ValueError: If database_url is invalid or empty string
        """
        # Resolve database URL from parameter, environment, or default
        if database_url is None:
            database_url = os.environ.get(ENV_DATABASE_URL)

        if not database_url:
            database_url = DEFAULT_DATABASE_URL

        if not database_url or not isinstance(database_url, str):
            raise ValueError("database_url must be a non-empty string")

        # Check if echo should be enabled via environment
        if os.environ.get(ENV_DATABASE_ECHO, "").lower() in ("1", "true", "yes"):
            echo = True

        # Configure connection arguments for SQLite
        if database_url.startswith("sqlite"):
            connect_args = connect_args or {"check_same_thread": False}

        # Create SQLAlchemy engine
        self.engine = create_engine(
            database_url,
            echo=echo,
            connect_args=connect_args,
            pool_pre_ping=True,  # Verify connections before using
        )

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

    def get_session(self) -> Session:
        """
        Create a new database session.

        Returns:
            New SQLAlchemy Session instance

        Example:
            >>> manager = SessionManager()
            >>> session = manager.get_session()
            >>> try:
            ...     users = session.query(User).all()
            ... finally:
            ...     session.close()
        """
        return self.SessionLocal()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Provide a transactional scope around a series of operations.

        Automatically commits or rolls back transactions and closes the session.

        Yields:
            SQLAlchemy Session instance

        Raises:
            SQLAlchemyError: If any database operation fails

        Example:
            >>> manager = SessionManager()
            >>> with manager.session_scope() as session:
            ...     user = User(name="Alice")
            ...     session.add(user)
            ...     # Automatically commits on success, rolls back on error
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        """
        Close the database engine and all connections.

        Call this when shutting down the application to ensure clean cleanup.
        """
        if hasattr(self, "engine") and self.engine:
            self.engine.dispose()

    def __enter__(self) -> SessionManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - closes connections."""
        self.close()


# Global session manager instance
_global_manager: Optional[SessionManager] = None


def get_global_manager() -> SessionManager:
    """
    Get or create the global session manager instance.

    Uses a singleton pattern to ensure only one database engine is created
    per process. Configuration is loaded from environment variables or defaults.

    Returns:
        Global SessionManager instance

    Example:
        >>> manager = get_global_manager()
        >>> session = manager.get_session()
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = SessionManager()
    return _global_manager


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database session injection.

    Provides a database session that is automatically closed after the request.
    Use this function with FastAPI's Depends() for automatic session management.

    Yields:
        SQLAlchemy Session instance

    Example:
        >>> from fastapi import Depends
        >>> @app.get("/users")
        >>> def list_users(db: Session = Depends(get_db)):
        ...     return db.query(User).all()
    """
    manager = get_global_manager()
    db = manager.get_session()
    try:
        yield db
    finally:
        db.close()


def init_db(
    database_url: Optional[str] = None,
    drop_tables: bool = False,
) -> None:
    """
    Initialize database by creating all tables.

    This function should be called once at application startup to create
    all database tables. It imports all models to ensure they are registered
    with SQLAlchemy's metadata.

    Args:
        database_url: Optional database URL. If None, uses environment or default.
        drop_tables: If True, drops all existing tables before creating new ones.
                     WARNING: This will delete all data!

    Raises:
        SQLAlchemyError: If database initialization fails

    Example:
        >>> # Initialize database with default settings
        >>> init_db()

        >>> # Drop and recreate all tables (for development/testing)
        >>> init_db(drop_tables=True)
    """
    # Import all models to ensure they're registered with SQLAlchemy
    # This import needs to happen here to avoid circular imports
    try:
        from autoflow.db import models  # noqa: F401
    except ImportError:
        # Models don't exist yet, which is fine for first-time setup
        pass

    manager = SessionManager(database_url=database_url)

    if drop_tables:
        from autoflow.db.models import Base

        Base.metadata.drop_all(bind=manager.engine)

    # Import and create all tables
    try:
        from autoflow.db.models import Base

        Base.metadata.create_all(bind=manager.engine)
    except ImportError:
        # No models defined yet, skip table creation
        pass

    manager.close()


def close_db() -> None:
    """
    Close the global database session manager.

    Call this during application shutdown to ensure clean cleanup of
    database connections.

    Example:
        >>> import atexit
        >>> atexit.register(close_db)
    """
    global _global_manager
    if _global_manager is not None:
        _global_manager.close()
        _global_manager = None
