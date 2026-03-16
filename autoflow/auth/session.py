"""
Autoflow Session Management Module

Provides enterprise session management with configurable policies including
session timeout, idle timeout, concurrent session limits, and secure token
generation. Integrates with authentication models for complete lifecycle
management of user sessions.

Usage:
    from autoflow.auth.session import SessionManager, SessionPolicy

    # Create a session manager with custom policy
    policy = SessionPolicy(
        session_timeout_hours=8,
        idle_timeout_minutes=30,
        max_concurrent_sessions=5
    )
    manager = SessionManager(policy=policy)

    # Create a session
    session = manager.create_session(
        user_id="user-123",
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0..."
    )

    # Validate a session
    if manager.is_valid_session(session.token):
        user_id = manager.get_user_id(session.token)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from autoflow.auth.models import Session, SessionStatus

logger = logging.getLogger(__name__)


class SessionCleanupStrategy(str, Enum):
    """Strategy for cleaning up expired sessions."""

    LAZY = "lazy"  # Clean up on access
    SCHEDULED = "scheduled"  # Clean up on timer
    MANUAL = "manual"  # Clean up only when explicitly requested


class SessionPolicy(BaseModel):
    """
    Configurable session management policies.

    Defines enterprise-grade session policies for security and compliance.
    Controls session lifetime, idle timeouts, concurrent sessions, and
    cleanup strategies.

    Attributes:
        session_timeout_hours: Maximum session lifetime in hours
        idle_timeout_minutes: Maximum idle time before session expires
        max_concurrent_sessions: Maximum active sessions per user
        remember_me_days: Extended session duration for "remember me"
        cleanup_strategy: When to clean up expired sessions
        enforce_ip_binding: Whether sessions are bound to IP address
        enforce_user_agent: Whether sessions are bound to user agent
        rotation_minutes: Session token rotation interval

    Example:
        >>> policy = SessionPolicy(
        ...     session_timeout_hours=8,
        ...     idle_timeout_minutes=30,
        ...     max_concurrent_sessions=5
        ... )
        >>> manager = SessionManager(policy=policy)
    """

    session_timeout_hours: float = 24.0
    idle_timeout_minutes: float = 60.0
    max_concurrent_sessions: int = 10
    remember_me_days: int = 30
    cleanup_strategy: SessionCleanupStrategy = SessionCleanupStrategy.LAZY
    enforce_ip_binding: bool = False
    enforce_user_agent: bool = False
    rotation_minutes: Optional[float] = None

    @field_validator("session_timeout_hours")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Validate session timeout is positive."""
        if v <= 0:
            raise ValueError("session_timeout_hours must be positive")
        return v

    @field_validator("idle_timeout_minutes")
    @classmethod
    def validate_idle_timeout(cls, v: float) -> float:
        """Validate idle timeout is positive."""
        if v <= 0:
            raise ValueError("idle_timeout_minutes must be positive")
        return v

    @field_validator("max_concurrent_sessions")
    @classmethod
    def validate_max_sessions(cls, v: int) -> int:
        """Validate max concurrent sessions is positive."""
        if v <= 0:
            raise ValueError("max_concurrent_sessions must be positive")
        return v

    @property
    def session_timeout(self) -> timedelta:
        """Get session timeout as timedelta."""
        return timedelta(hours=self.session_timeout_hours)

    @property
    def idle_timeout(self) -> timedelta:
        """Get idle timeout as timedelta."""
        return timedelta(minutes=self.idle_timeout_minutes)

    @property
    def remember_me_duration(self) -> timedelta:
        """Get remember me duration as timedelta."""
        return timedelta(days=self.remember_me_days)

    @property
    def rotation_interval(self) -> Optional[timedelta]:
        """Get token rotation interval as timedelta."""
        if self.rotation_minutes is None:
            return None
        return timedelta(minutes=self.rotation_minutes)


class SessionManager:
    """
    Manages user sessions with configurable policies.

    Provides enterprise session lifecycle management including creation,
    validation, refresh, revocation, and cleanup. Enforces session policies
    for security and compliance.

    Thread-safe operations for use in web applications and APIs.

    Attributes:
        policy: Session management policy
        sessions: In-memory session storage (indexed by token)
        user_sessions: Index of sessions by user_id

    Example:
        >>> manager = SessionManager()
        >>> session = manager.create_session("user-123")
        >>> if manager.is_valid_session(session.token):
        ...     manager.refresh_session(session.token)
    """

    def __init__(self, policy: Optional[SessionPolicy] = None):
        """
        Initialize the SessionManager.

        Args:
            policy: Session policy (defaults to SessionPolicy())
        """
        self.policy = policy or SessionPolicy()
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, list[str]] = {}

    # === Session Creation ===

    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        remember_me: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Session:
        """
        Create a new user session.

        Enforces concurrent session limits by revoking oldest sessions
        when the limit is exceeded.

        Args:
            user_id: User ID to create session for
            ip_address: Optional IP address for binding
            user_agent: Optional user agent for binding
            remember_me: Whether to use extended session duration
            metadata: Optional session metadata

        Returns:
            Created session object

        Raises:
            ValueError: If user_id is empty

        Example:
            >>> session = manager.create_session(
            ...     user_id="user-123",
            ...     ip_address="192.168.1.1",
            ...     remember_me=True
            ... )
            >>> session.user_id
            'user-123'
        """
        if not user_id:
            raise ValueError("user_id is required")

        # Determine session expiration
        if remember_me:
            expires_at = datetime.utcnow() + self.policy.remember_me_duration
        else:
            expires_at = datetime.utcnow() + self.policy.session_timeout

        # Create session
        session = Session(
            user_id=user_id,
            expires_at=expires_at,
            ip_address=ip_address if self.policy.enforce_ip_binding else None,
            user_agent=user_agent if self.policy.enforce_user_agent else None,
            metadata=metadata or {},
        )

        # Enforce concurrent session limit
        self._enforce_concurrent_limit(user_id)

        # Store session
        self._sessions[session.token] = session
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session.token)

        logger.info(
            f"Created session {session.id} for user {user_id} "
            f"(expires: {expires_at.isoformat()})"
        )

        return session

    # === Session Validation ===

    def is_valid_session(
        self,
        token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Check if a session token is valid.

        Validates session status, expiration, and optional IP/user agent binding.

        Args:
            token: Session token to validate
            ip_address: Optional IP address to verify binding
            user_agent: Optional user agent to verify binding

        Returns:
            True if session is valid, False otherwise

        Example:
            >>> if manager.is_valid_session(token):
            ...     user_id = manager.get_user_id(token)
        """
        session = self._sessions.get(token)
        if not session:
            return False

        # Check if session is expired
        if session.is_expired:
            self._mark_session_expired(session)
            return False

        # Check session status
        if session.status != SessionStatus.ACTIVE:
            return False

        # Check IP binding if enforced
        if self.policy.enforce_ip_binding and ip_address:
            if session.ip_address != ip_address:
                logger.warning(
                    f"Session {session.id} IP mismatch: "
                    f"{session.ip_address} != {ip_address}"
                )
                return False

        # Check user agent binding if enforced
        if self.policy.enforce_user_agent and user_agent:
            if session.user_agent != user_agent:
                logger.warning(
                    f"Session {session.id} user agent mismatch: "
                    f"{session.user_agent} != {user_agent}"
                )
                return False

        # Check idle timeout
        if self._is_session_idle(session):
            self._mark_session_expired(session)
            return False

        return True

    def get_session(self, token: str) -> Optional[Session]:
        """
        Get a session by token.

        Args:
            token: Session token

        Returns:
            Session object or None if not found

        Example:
            >>> session = manager.get_session(token)
            >>> if session:
            ...     print(session.user_id)
        """
        return self._sessions.get(token)

    def get_user_id(self, token: str) -> Optional[str]:
        """
        Get user ID from session token.

        Args:
            token: Session token

        Returns:
            User ID or None if session invalid

        Example:
            >>> user_id = manager.get_user_id(token)
            >>> if user_id:
            ...     print(f"Authenticated as {user_id}")
        """
        session = self._sessions.get(token)
        if session and self.is_valid_session(token):
            return session.user_id
        return None

    # === Session Operations ===

    def refresh_session(
        self,
        token: str,
        ip_address: Optional[str] = None,
    ) -> Optional[Session]:
        """
        Refresh a session's expiration time.

        Extends session expiration and updates last activity.

        Args:
            token: Session token to refresh
            ip_address: Optional IP address for binding

        Returns:
            Refreshed session or None if not found/invalid

        Example:
            >>> session = manager.refresh_session(token)
            >>> if session:
            ...     print(f"Session extended until {session.expires_at}")
        """
        session = self._sessions.get(token)
        if not session:
            return None

        if not self.is_valid_session(token, ip_address=ip_address):
            return None

        session.refresh(duration=self.policy.session_timeout)
        session.record_activity(ip_address=ip_address)

        logger.info(f"Refreshed session {session.id} for user {session.user_id}")

        return session

    def revoke_session(self, token: str) -> bool:
        """
        Revoke a session.

        Args:
            token: Session token to revoke

        Returns:
            True if session was revoked, False if not found

        Example:
            >>> manager.revoke_session(token)
            True
        """
        session = self._sessions.get(token)
        if not session:
            return False

        session.revoke()
        self._remove_from_user_index(session)

        logger.info(f"Revoked session {session.id} for user {session.user_id}")

        return True

    def revoke_user_sessions(
        self,
        user_id: str,
        except_token: Optional[str] = None,
    ) -> int:
        """
        Revoke all sessions for a user.

        Args:
            user_id: User ID to revoke sessions for
            except_token: Optional token to exclude from revocation

        Returns:
            Number of sessions revoked

        Example:
            >>> count = manager.revoke_user_sessions("user-123")
            >>> print(f"Revoked {count} sessions")
        """
        if user_id not in self._user_sessions:
            return 0

        tokens = self._user_sessions[user_id][:]
        revoked = 0

        for token in tokens:
            if token == except_token:
                continue
            if self.revoke_session(token):
                revoked += 1

        logger.info(f"Revoked {revoked} sessions for user {user_id}")

        return revoked

    # === Session Cleanup ===

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.

        Removes sessions that are expired or have been idle too long.

        Returns:
            Number of sessions cleaned up

        Example:
            >>> cleaned = manager.cleanup_expired_sessions()
            >>> print(f"Cleaned up {cleaned} expired sessions")
        """
        now = datetime.utcnow()
        expired_tokens = []

        for token, session in self._sessions.items():
            # Check explicit expiration
            if session.is_expired:
                expired_tokens.append(token)
                continue

            # Check idle timeout
            if self._is_session_idle(session):
                expired_tokens.append(token)
                continue

        # Remove expired sessions
        for token in expired_tokens:
            session = self._sessions.get(token)
            if session:
                self._mark_session_expired(session)
                del self._sessions[token]
                self._remove_from_user_index(session)

        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")

        return len(expired_tokens)

    # === Session Queries ===

    def get_user_sessions(self, user_id: str) -> list[Session]:
        """
        Get all active sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of active sessions

        Example:
            >>> sessions = manager.get_user_sessions("user-123")
            >>> print(f"User has {len(sessions)} active sessions")
        """
        if user_id not in self._user_sessions:
            return []

        sessions = []
        for token in self._user_sessions[user_id]:
            session = self._sessions.get(token)
            if session and session.status == SessionStatus.ACTIVE:
                sessions.append(session)

        return sessions

    def get_session_count(self, user_id: Optional[str] = None) -> int:
        """
        Get count of active sessions.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            Number of active sessions

        Example:
            >>> count = manager.get_session_count()
            >>> print(f"Total active sessions: {count}")
        """
        if user_id:
            return len(self.get_user_sessions(user_id))
        return len(
            [s for s in self._sessions.values() if s.status == SessionStatus.ACTIVE]
        )

    # === Internal Methods ===

    def _enforce_concurrent_limit(self, user_id: str) -> None:
        """
        Enforce concurrent session limit for a user.

        Revokes oldest sessions when limit is exceeded.

        Args:
            user_id: User ID to enforce limit for
        """
        user_tokens = self._user_sessions.get(user_id, [])

        while len(user_tokens) >= self.policy.max_concurrent_sessions:
            # Revoke oldest session
            oldest_token = user_tokens.pop(0)
            oldest_session = self._sessions.get(oldest_token)
            if oldest_session:
                oldest_session.revoke()
                del self._sessions[oldest_token]
                logger.info(
                    f"Revoked oldest session {oldest_session.id} "
                    f"for user {user_id} due to concurrent limit"
                )

    def _is_session_idle(self, session: Session) -> bool:
        """
        Check if session has exceeded idle timeout.

        Args:
            session: Session to check

        Returns:
            True if session is idle
        """
        idle_time = datetime.utcnow() - session.last_activity
        return idle_time > self.policy.idle_timeout

    def _mark_session_expired(self, session: Session) -> None:
        """
        Mark a session as expired.

        Args:
            session: Session to mark
        """
        session.status = SessionStatus.EXPIRED
        session.updated_at = datetime.utcnow()

    def _remove_from_user_index(self, session: Session) -> None:
        """
        Remove session from user index.

        Args:
            session: Session to remove
        """
        if session.user_id in self._user_sessions:
            try:
                self._user_sessions[session.user_id].remove(session.token)
                # Clean up empty lists
                if not self._user_sessions[session.user_id]:
                    del self._user_sessions[session.user_id]
            except ValueError:
                pass  # Token not in list

    # === Utility Methods ===

    def get_stats(self) -> dict[str, Any]:
        """
        Get session statistics.

        Returns:
            Dictionary with session statistics

        Example:
            >>> stats = manager.get_stats()
            >>> print(f"Total sessions: {stats['total_sessions']}")
        """
        active = [
            s
            for s in self._sessions.values()
            if s.status == SessionStatus.ACTIVE and not s.is_expired
        ]
        expired = [
            s for s in self._sessions.values() if s.status == SessionStatus.EXPIRED
        ]
        revoked = [
            s for s in self._sessions.values() if s.status == SessionStatus.REVOKED
        ]

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len(active),
            "expired_sessions": len(expired),
            "revoked_sessions": len(revoked),
            "unique_users": len(self._user_sessions),
            "policy": {
                "session_timeout_hours": self.policy.session_timeout_hours,
                "idle_timeout_minutes": self.policy.idle_timeout_minutes,
                "max_concurrent_sessions": self.policy.max_concurrent_sessions,
            },
        }
