"""
Autoflow Authentication Models

Provides Pydantic models for authentication, session management, and tokens.
These models integrate with the database layer while providing clean
API interfaces for authentication operations.

Usage:
    from autoflow.auth.models import User, Session, Token, SessionStatus

    # Create a user model from database user
    user = User.from_db_user(db_user)

    # Create a session
    session = Session(
        user_id=user.id,
        token="abc123...",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )

    # Create an API token
    token = Token(
        user_id=user.id,
        name="CI/CD Token",
        scopes=["specs:read", "tasks:write"]
    )
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from autoflow.db.models import User as DBUser


class SessionStatus(str, Enum):
    """Status of a user session."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALID = "invalid"


class TokenType(str, Enum):
    """Type of authentication token."""

    SESSION = "session"
    API = "api"
    PERSONAL_ACCESS = "personal_access"
    SERVICE_ACCOUNT = "service_account"


class User(BaseModel):
    """
    Represents a user in the authentication layer.

    This is a Pydantic model that wraps the database User model,
    providing a clean interface for authentication operations.
    It excludes sensitive information like password hashes.

    Attributes:
        id: Unique user identifier
        email: User's email address
        name: User's full display name
        sso_provider: SSO provider used for authentication
        status: Current account status
        is_superuser: Admin bypass flag
        created_at: Account creation timestamp
        updated_at: Last update timestamp
        last_login: Most recent successful login

    Example:
        >>> user = User(
        ...     id="user-123",
        ...     email="user@example.com",
        ...     name="John Doe"
        ... )
        >>> user.is_active
        True
    """

    id: str
    email: str
    name: str
    sso_provider: str = "none"
    status: str = "pending"
    is_superuser: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == "active"

    @property
    def is_pending(self) -> bool:
        """Check if user account is pending activation."""
        return self.status == "pending"

    @property
    def is_suspended(self) -> bool:
        """Check if user account is suspended."""
        return self.status == "suspended"

    @classmethod
    def from_db_user(cls, db_user: "DBUser") -> "User":
        """
        Create a User model from a database User.

        Args:
            db_user: SQLAlchemy database User model

        Returns:
            User model instance

        Example:
            >>> user = User.from_db_user(db_user)
            >>> user.email
            'user@example.com'
        """
        return cls(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name,
            sso_provider=db_user.sso_provider.value,
            status=db_user.status.value,
            is_superuser=db_user.is_superuser,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
            last_login=db_user.last_login,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert user to dictionary representation.

        Excludes sensitive fields and includes computed properties.

        Returns:
            Dictionary with user data

        Example:
            >>> user_dict = user.to_dict()
            >>> user_dict["is_active"]
            True
        """
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "sso_provider": self.sso_provider,
            "status": self.status,
            "is_superuser": self.is_superuser,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class Session(BaseModel):
    """
    Represents a user session for authentication.

    Sessions track active user logins with expiration and metadata.
    Used for managing web sessions and API authentication.

    Attributes:
        id: Unique session identifier
        user_id: ID of the user this session belongs to
        token: Session token (typically JWT or random string)
        status: Current session status
        expires_at: Session expiration timestamp
        created_at: Session creation timestamp
        updated_at: Last activity timestamp
        last_activity: Last user activity timestamp
        ip_address: IP address of session creation
        user_agent: Browser/client user agent
        metadata: Additional session data

    Example:
        >>> session = Session(
        ...     user_id="user-123",
        ...     token="abc123...",
        ...     expires_at=datetime.utcnow() + timedelta(hours=1)
        ... )
        >>> session.is_valid
        True
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    token: str = Field(default_factory=lambda: _generate_token())
    status: SessionStatus = SessionStatus.ACTIVE
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=24)
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if session is valid (active and not expired)."""
        if self.status != SessionStatus.ACTIVE:
            return False
        return datetime.utcnow() < self.expires_at

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() >= self.expires_at

    @property
    def time_remaining(self) -> timedelta:
        """Get remaining time until session expires."""
        if self.is_expired:
            return timedelta(0)
        return self.expires_at - datetime.utcnow()

    def refresh(self, duration: timedelta = timedelta(hours=24)) -> None:
        """
        Refresh session expiration time.

        Args:
            duration: Time until session expires (default: 24 hours)

        Example:
            >>> session.refresh(timedelta(hours=8))
            >>> session.expires_at > datetime.utcnow()
            True
        """
        self.expires_at = datetime.utcnow() + duration
        self.updated_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()

    def revoke(self) -> None:
        """
        Revoke the session.

        Example:
            >>> session.revoke()
            >>> session.status
            'revoked'
        """
        self.status = SessionStatus.REVOKED
        self.updated_at = datetime.utcnow()

    def record_activity(self, ip_address: Optional[str] = None) -> None:
        """
        Record user activity on the session.

        Args:
            ip_address: Optional IP address of the activity

        Example:
            >>> session.record_activity(ip_address="192.168.1.1")
            >>> session.last_activity > datetime.utcnow() - timedelta(seconds=1)
            True
        """
        self.last_activity = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if ip_address:
            self.ip_address = ip_address

    def to_dict(self, include_token: bool = False) -> dict[str, Any]:
        """
        Convert session to dictionary representation.

        Args:
            include_token: Whether to include the session token

        Returns:
            Dictionary with session data

        Example:
            >>> session_dict = session.to_dict(include_token=False)
            >>> "token" not in session_dict
            True
        """
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "status": self.status.value,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_valid": self.is_valid,
            "is_expired": self.is_expired,
        }
        if include_token:
            data["token"] = self.token
        if self.ip_address:
            data["ip_address"] = self.ip_address
        if self.user_agent:
            data["user_agent"] = self.user_agent
        return data


class Token(BaseModel):
    """
    Represents an authentication token.

    Tokens are used for API access, personal access tokens, and service accounts.
    Unlike sessions, tokens are long-lived and don't expire automatically.

    Attributes:
        id: Unique token identifier
        user_id: ID of the user who owns the token
        name: Human-readable token name
        token: The actual token value (hashed when stored)
        token_type: Type of token (API, personal access, service account)
        scopes: List of permission scopes granted to this token
        expires_at: Optional token expiration timestamp
        last_used: Last time the token was used
        created_at: Token creation timestamp
        is_active: Whether the token is currently active
        metadata: Additional token data

    Example:
        >>> token = Token(
        ...     user_id="user-123",
        ...     name="CI/CD Token",
        ...     scopes=["specs:read", "tasks:write"]
        ... )
        >>> token.has_scope("specs:read")
        True
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    name: str
    token: str = Field(default_factory=lambda: _generate_token())
    token_type: TokenType = TokenType.API
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        """
        Validate token scopes.

        Ensures scopes are in the correct format (resource:action).

        Args:
            v: List of scopes to validate

        Returns:
            Validated scopes

        Raises:
            ValueError: If any scope is invalid
        """
        for scope in v:
            if not isinstance(scope, str) or ":" not in scope:
                raise ValueError(
                    f"Invalid scope '{scope}'. Must be in format 'resource:action'"
                )
        return v

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (active and not expired)."""
        if not self.is_active:
            return False
        return not self.is_expired

    def has_scope(self, scope: str) -> bool:
        """
        Check if token has a specific scope.

        Args:
            scope: Scope to check (e.g., "specs:read")

        Returns:
            True if token has the scope, False otherwise

        Example:
            >>> token.has_scope("specs:read")
            True
        """
        return scope in self.scopes

    def has_any_scope(self, scopes: list[str]) -> bool:
        """
        Check if token has any of the specified scopes.

        Args:
            scopes: List of scopes to check

        Returns:
            True if token has at least one of the scopes

        Example:
            >>> token.has_any_scope(["specs:read", "specs:write"])
            True
        """
        return any(scope in self.scopes for scope in scopes)

    def revoke(self) -> None:
        """
        Revoke the token.

        Example:
            >>> token.revoke()
            >>> token.is_active
            False
        """
        self.is_active = False

    def record_usage(self) -> None:
        """
        Record token usage.

        Updates the last_used timestamp to current time.

        Example:
            >>> token.record_usage()
            >>> token.last_used > datetime.utcnow() - timedelta(seconds=1)
            True
        """
        self.last_used = datetime.utcnow()

    def to_dict(self, include_token: bool = False) -> dict[str, Any]:
        """
        Convert token to dictionary representation.

        Args:
            include_token: Whether to include the token value

        Returns:
            Dictionary with token data

        Example:
            >>> token_dict = token.to_dict(include_token=False)
            >>> "token" not in token_dict
            True
        """
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "token_type": self.token_type.value,
            "scopes": self.scopes,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "is_valid": self.is_valid,
        }
        if include_token:
            data["token"] = self.token
        return data


def _generate_token() -> str:
    """
    Generate a cryptographically random token.

    Returns:
        URL-safe base64 encoded random token

    Example:
        >>> token = _generate_token()
        >>> len(token) > 32
        True
    """
    import secrets

    return secrets.token_urlsafe(32)
