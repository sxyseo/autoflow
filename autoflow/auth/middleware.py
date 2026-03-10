"""
Autoflow Authentication Middleware Module

Provides FastAPI middleware for request authentication and authorization.
Intercepts incoming requests, validates session tokens, and integrates with
RBAC for fine-grained access control.

Usage:
    from autoflow.auth.middleware import AuthMiddleware, get_current_user, require_auth

    # Add middleware to FastAPI app
    app.add_middleware(AuthMiddleware)

    # Use in route handlers
    @app.get("/protected")
    async def protected_route(user: User = require_auth):
        return {"message": f"Hello {user.name}"}

    @app.get("/optional")
    async def optional_route(user: Optional[User] = get_current_user):
        if user:
            return {"message": f"Hello {user.name}"}
        return {"message": "Hello guest"}
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional, Union

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from autoflow.auth.models import Session, User
from autoflow.auth.rbac import PermissionChecker, Role
from autoflow.auth.session import SessionManager

logger = logging.getLogger(__name__)


# Global session manager instance (will be initialized during app startup)
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager instance

    Raises:
        RuntimeError: If session manager has not been initialized
    """
    global _session_manager
    if _session_manager is None:
        raise RuntimeError(
            "SessionManager not initialized. Call init_auth_middleware() during app startup."
        )
    return _session_manager


def init_auth_middleware(session_manager: SessionManager) -> None:
    """
    Initialize authentication middleware with a session manager.

    Call this during application startup to configure the auth system.

    Args:
        session_manager: SessionManager instance for session validation

    Example:
        >>> from autoflow.auth.session import SessionManager
        >>> from autoflow.auth.middleware import init_auth_middleware
        >>>
        >>> manager = SessionManager()
        >>> init_auth_middleware(manager)
    """
    global _session_manager
    _session_manager = session_manager
    logger.info("Authentication middleware initialized")


class AuthScheme(str, Enum):
    """Authentication scheme types."""

    HEADER = "header"  # Authorization header
    COOKIE = "cookie"  # Session cookie
    QUERY = "query"  # Query parameter (for testing only)


class AuthConfig(BaseModel):
    """
    Configuration for authentication middleware.

    Defines how authentication is performed, including token sources,
    required authentication for endpoints, and error handling behavior.

    Attributes:
        auth_scheme: Where to look for authentication tokens
        header_name: Name of Authorization header (default: "Authorization")
        cookie_name: Name of session cookie (default: "session")
        query_param: Name of query parameter (default: "token")
        require_auth_by_default: Whether auth is required unless explicitly marked optional
        allow_anonymous_paths: Paths that don't require authentication (supports wildcards)
        auto_refresh: Whether to automatically refresh sessions on each request
        audit_events: Whether to log authentication events to audit log

    Example:
        >>> config = AuthConfig(
        ...     auth_scheme=AuthScheme.HEADER,
        ...     require_auth_by_default=False,
        ...     allow_anonymous_paths=["/health", "/api/v1/info", "/docs"]
        ... )
    """

    auth_scheme: AuthScheme = AuthScheme.HEADER
    header_name: str = "Authorization"
    cookie_name: str = "session"
    query_param: str = "token"
    require_auth_by_default: bool = False
    allow_anonymous_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/api/v1/info", "/docs", "/redoc", "/openapi.json"]
    )
    auto_refresh: bool = True
    audit_events: bool = True


class AuthContext(BaseModel):
    """
    Authentication context attached to requests.

    Contains user and session information extracted from the request token.
    Attached to request.state for use in route handlers.

    Attributes:
        user: Authenticated user (None if not authenticated)
        session: User session (None if not authenticated)
        token: Session token (None if not authenticated)
        is_authenticated: Whether the request is authenticated
        is_superuser: Whether the user is a superuser

    Example:
        >>> ctx = AuthContext(user=user, session=session, token="abc123")
        >>> ctx.is_authenticated
        True
        >>> ctx.user.email
        'user@example.com'
    """

    user: Optional[User] = None
    session: Optional[Session] = None
    token: Optional[str] = None
    is_authenticated: bool = False
    is_superuser: bool = False


class AuthMiddleware:
    """
    FastAPI middleware for authentication and authorization.

    Intercepts incoming requests, extracts and validates session tokens,
    and attaches authentication context to the request. Integrates with
    SessionManager for session validation and RBAC for authorization.

    Usage:
        >>> from fastapi import FastAPI
        >>> from autoflow.auth.middleware import AuthMiddleware
        >>>
        >>> app = FastAPI()
        >>> app.add_middleware(AuthMiddleware, config=AuthConfig())

    The middleware:
    1. Extracts token from Authorization header, cookie, or query param
    2. Validates session using SessionManager
    3. Loads user and attaches to request.state
    4. Optionally refreshes session on activity
    5. Logs authentication events for audit

    Example:
        >>> middleware = AuthMiddleware(config=AuthConfig())
        >>> # middleware is added to FastAPI app
    """

    def __init__(self, app, config: Optional[AuthConfig] = None):
        """
        Initialize the authentication middleware.

        Args:
            app: FastAPI application instance
            config: Optional authentication configuration

        Example:
            >>> middleware = AuthMiddleware(
            ...     app,
            ...     config=AuthConfig(require_auth_by_default=True)
            ... )
        """
        self.app = app
        self.config = config or AuthConfig()
        self.security = HTTPBearer(auto_error=False)

        # Validate configuration
        if not self.config.allow_anonymous_paths:
            self.config.allow_anonymous_paths = []

        logger.info(
            f"AuthMiddleware initialized with scheme: {self.config.auth_scheme.value}"
        )

    async def __call__(self, request: Request, call_next):
        """
        Process incoming request through middleware.

        Extracts authentication token, validates session, attaches
        authentication context to request state, and proceeds to
        next middleware or route handler.

        Args:
            request: Incoming request
            call_next: Next middleware or route handler

        Returns:
            Response from route handler

        Raises:
            HTTPException: If authentication fails and is required
        """
        # Check if path allows anonymous access
        if self._is_anonymous_path(request.url.path):
            logger.debug(f"Allowing anonymous access to {request.url.path}")
            request.state.auth = AuthContext()
            return await call_next(request)

        # Extract token from request
        token = self._extract_token(request)

        # Validate token and get session
        auth_context = await self._authenticate_request(request, token)

        # Attach auth context to request state
        request.state.auth = auth_context

        # Check if authentication is required
        if (
            self.config.require_auth_by_default
            and not auth_context.is_authenticated
            and not self._is_anonymous_path(request.url.path)
        ):
            logger.warning(f"Authentication required for {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Auto-refresh session if enabled
        if (
            self.config.auto_refresh
            and auth_context.is_authenticated
            and auth_context.session
        ):
            await self._refresh_session(request, auth_context.session)

        # Log authentication event if enabled
        if self.config.audit_events:
            await self._log_auth_event(request, auth_context)

        # Proceed to next middleware/route
        return await call_next(request)

    def _is_anonymous_path(self, path: str) -> bool:
        """
        Check if path allows anonymous access.

        Supports wildcard patterns using simple glob matching.

        Args:
            path: Request path to check

        Returns:
            True if path allows anonymous access
        """
        for pattern in self.config.allow_anonymous_paths:
            # Simple wildcard matching
            if "*" in pattern:
                regex_pattern = pattern.replace("*", ".*")
                import re

                if re.fullmatch(regex_pattern, path):
                    return True
            elif path == pattern:
                return True
        return False

    async def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract authentication token from request.

        Tries multiple sources based on configured auth scheme.

        Args:
            request: Incoming request

        Returns:
            Token string or None if not found
        """
        token = None

        # Try Authorization header
        if self.config.auth_scheme in [AuthScheme.HEADER, AuthScheme.HEADER]:
            credentials: Optional[HTTPAuthorizationCredentials] = await self.security(
                request
            )
            if credentials:
                token = credentials.credentials
                logger.debug("Extracted token from Authorization header")

        # Try cookie
        if not token and self.config.auth_scheme in [
            AuthScheme.COOKIE,
            AuthScheme.COOKIE,
        ]:
            token = request.cookies.get(self.config.cookie_name)
            if token:
                logger.debug(f"Extracted token from cookie: {self.config.cookie_name}")

        # Try query parameter (for testing only)
        if not token and self.config.auth_scheme in [AuthScheme.QUERY, AuthScheme.QUERY]:
            token = request.query_params.get(self.config.query_param)
            if token:
                logger.debug(f"Extracted token from query param: {self.config.query_param}")

        return token

    async def _authenticate_request(
        self, request: Request, token: Optional[str]
    ) -> AuthContext:
        """
        Authenticate request using token.

        Validates session and loads user information.

        Args:
            request: Incoming request
            token: Session token to validate

        Returns:
            AuthContext with authentication information
        """
        if not token:
            return AuthContext()

        try:
            # Get session manager
            session_manager = get_session_manager()

            # Validate session
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

            if not session_manager.is_valid_session(
                token, ip_address=ip_address, user_agent=user_agent
            ):
                logger.warning(f"Invalid or expired token: {token[:8]}...")
                return AuthContext()

            # Get session and user_id
            session = session_manager.get_session(token)
            if not session:
                return AuthContext()

            user_id = session_manager.get_user_id(token)
            if not user_id:
                return AuthContext()

            # Load user from database
            # TODO: Load actual user from database
            # For now, create a minimal user object
            user = User(
                id=user_id,
                email=f"{user_id}@example.com",  # Placeholder
                name=f"User {user_id}",  # Placeholder
                status="active",
            )

            logger.debug(f"Authenticated user: {user_id}")

            return AuthContext(
                user=user,
                session=session,
                token=token,
                is_authenticated=True,
                is_superuser=user.is_superuser,
            )

        except Exception as e:
            logger.error(f"Error during authentication: {e}", exc_info=True)
            return AuthContext()

    async def _refresh_session(self, request: Request, session: Session) -> None:
        """
        Refresh session on activity.

        Args:
            request: Incoming request
            session: Session to refresh
        """
        try:
            session_manager = get_session_manager()
            ip_address = request.client.host if request.client else None

            session_manager.refresh_session(session.token, ip_address=ip_address)
            logger.debug(f"Refreshed session: {session.id}")

        except Exception as e:
            logger.error(f"Error refreshing session: {e}", exc_info=True)

    async def _log_auth_event(self, request: Request, auth_context: AuthContext) -> None:
        """
        Log authentication event to audit log.

        Args:
            request: Incoming request
            auth_context: Authentication context
        """
        try:
            # Import here to avoid circular dependencies
            from autoflow.auth.audit import track_login, track_logout

            if auth_context.is_authenticated:
                # Track successful authentication
                user_id = auth_context.user.id if auth_context.user else None
                ip_address = request.client.host if request.client else None

                # Only log if not already tracked recently (avoid spam)
                # For now, just log at debug level
                logger.debug(
                    f"Authenticated request: {request.method} {request.url.path} "
                    f"by user {user_id} from {ip_address}"
                )

        except Exception as e:
            logger.error(f"Error logging auth event: {e}", exc_info=True)


# === FastAPI Dependencies ===


async def get_current_user(request: Request) -> Optional[User]:
    """
    FastAPI dependency to get current authenticated user.

    Returns None if user is not authenticated (optional authentication).

    Args:
        request: FastAPI request object

    Returns:
        User object or None if not authenticated

    Example:
        >>> @app.get("/profile")
        ... async def get_profile(user: Optional[User] = Depends(get_current_user)):
        ...     if not user:
        ...         return {"message": "Not logged in"}
        ...     return {"email": user.email}
    """
    auth_context: AuthContext = getattr(request.state, "auth", AuthContext())
    return auth_context.user


async def get_current_user_required(request: Request) -> User:
    """
    FastAPI dependency to get current authenticated user (required).

    Raises HTTPException if user is not authenticated.

    Args:
        request: FastAPI request object

    Returns:
        User object

    Raises:
        HTTPException: If user is not authenticated

    Example:
        >>> @app.get("/profile")
        ... async def get_profile(user: User = Depends(get_current_user_required)):
        ...     return {"email": user.email}
    """
    auth_context: AuthContext = getattr(request.state, "auth", AuthContext())

    if not auth_context.is_authenticated or not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return auth_context.user


async def get_current_session(request: Request) -> Optional[Session]:
    """
    FastAPI dependency to get current session.

    Returns None if session is not available.

    Args:
        request: FastAPI request object

    Returns:
        Session object or None

    Example:
        >>> @app.get("/session-info")
        ... async def session_info(session: Optional[Session] = Depends(get_current_session)):
        ...     if not session:
        ...         return {"message": "No active session"}
        ...     return {"expires_at": session.expires_at}
    """
    auth_context: AuthContext = getattr(request.state, "auth", AuthContext())
    return auth_context.session


async def require_auth(request: Request) -> User:
    """
    Alias for get_current_user_required.

    Requires authentication and returns the current user.

    Args:
        request: FastAPI request object

    Returns:
        Authenticated user object

    Example:
        >>> @app.get("/protected")
        ... async def protected_route(user: User = Depends(require_auth)):
        ...     return {"message": f"Hello {user.name}"}
    """
    return await get_current_user_required(request)


async def require_superuser(request: Request) -> User:
    """
    FastAPI dependency to require superuser authentication.

    Raises HTTPException if user is not a superuser.

    Args:
        request: FastAPI request object

    Returns:
        Superuser object

    Raises:
        HTTPException: If user is not authenticated or not a superuser

    Example:
        >>> @app.get("/admin")
        ... async def admin_route(user: User = Depends(require_superuser)):
        ...     return {"message": f"Welcome admin {user.name}"}
    """
    user = await get_current_user_required(request)

    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )

    return user


# === Permission Dependencies ===


async def require_permission(permission: str):
    """
    FastAPI dependency factory to require specific permission.

    Args:
        permission: Permission name (e.g., "specs:write")

    Returns:
        Dependency function that checks the permission

    Example:
        >>> @app.post("/specs")
        ... async def create_spec(
        ...     user: User = Depends(require_permission("specs:write"))
        ... ):
        ...     return {"message": "Spec created"}
    """

    async def check_permission(request: Request) -> User:
        user = await get_current_user_required(request)

        # TODO: Load user roles and check permission
        # For now, just check if user is superuser
        if not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )

        return user

    return check_permission


async def require_role(role_name: str):
    """
    FastAPI dependency factory to require specific role.

    Args:
        role_name: Name of role required

    Returns:
        Dependency function that checks the role

    Example:
        >>> @app.post("/admin")
        ... async def admin_only(
        ...     user: User = Depends(require_role("admin"))
        ... ):
        ...     return {"message": "Welcome admin"}
    """

    async def check_role(request: Request) -> User:
        user = await get_current_user_required(request)

        # TODO: Load user roles and check role
        # For now, just check if user is superuser
        if not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' required",
            )

        return user

    return check_role


# === Utility Functions ===


def is_authenticated(request: Request) -> bool:
    """
    Check if request is authenticated.

    Args:
        request: FastAPI request object

    Returns:
        True if request is authenticated

    Example:
        >>> if is_authenticated(request):
        ...     user = request.state.auth.user
    """
    auth_context: AuthContext = getattr(request.state, "auth", AuthContext())
    return auth_context.is_authenticated


def get_auth_context(request: Request) -> AuthContext:
    """
    Get authentication context from request.

    Args:
        request: FastAPI request object

    Returns:
        AuthContext object

    Example:
        >>> ctx = get_auth_context(request)
        >>> if ctx.is_authenticated:
        ...     print(f"User: {ctx.user.email}")
    """
    return getattr(request.state, "auth", AuthContext())
