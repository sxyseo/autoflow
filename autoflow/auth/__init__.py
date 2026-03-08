"""
Autoflow Authentication Module

Provides authentication models, session management, and SSO integration
for enterprise identity management.

Usage:
    from autoflow.auth.models import User, Session, Token
    from autoflow.auth.session import SessionManager, SessionPolicy
    from autoflow.auth.sso import SAMLProvider, OIDCProvider

    # Create a user session
    session = Session(
        user_id="user-123",
        token="abc123...",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )

    # Create a session manager with custom policy
    policy = SessionPolicy(session_timeout_hours=8)
    manager = SessionManager(policy=policy)
    session = manager.create_session(user_id="user-123")
"""

from __future__ import annotations

from autoflow.auth.models import Session, Token, User
from autoflow.auth.session import SessionManager, SessionPolicy

__all__ = [
    "User",
    "Session",
    "Token",
    "SessionManager",
    "SessionPolicy",
]
