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

    # Track authentication events
    from autoflow.auth.audit import track_login, track_permission_check
    track_login(user_id="user-123", success=True, ip_address="192.168.1.1")
    track_permission_check(user_id="user-123", permission="spec:write", granted=True)
"""

from __future__ import annotations

from autoflow.auth.audit import (
    AuditEvent,
    AuditLogger,
    AuditLog,
    AuditSeverity,
    get_compliance_export,
    log_auth_event,
    track_login,
    track_logout,
    track_permission_check,
    track_role_assignment,
    track_role_removal,
    track_session_created,
    track_session_revoked,
    track_sso_login,
)
from autoflow.auth.models import Session, Token, User
from autoflow.auth.session import SessionManager, SessionPolicy

__all__ = [
    # Models
    "User",
    "Session",
    "Token",
    "SessionManager",
    "SessionPolicy",
    # Audit
    "AuditEvent",
    "AuditLogger",
    "AuditLog",
    "AuditSeverity",
    "track_login",
    "track_logout",
    "track_permission_check",
    "track_role_assignment",
    "track_role_removal",
    "track_session_created",
    "track_session_revoked",
    "track_sso_login",
    "log_auth_event",
    "get_compliance_export",
]
