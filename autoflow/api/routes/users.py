"""
Autoflow User Management API Routes

Provides endpoints for managing users, roles, and permissions.
Supports user CRUD operations, role assignment, and status management.
Integrates with the database models for RBAC functionality.

Usage:
    from fastapi import FastAPI
    from autoflow.api.routes.users import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/users", tags=["User Management"])
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from autoflow.auth import SessionManager

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Security scheme for bearer token authentication
security = HTTPBearer(auto_error=False)

# Global session manager (initialized on startup)
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager instance

    Raises:
        HTTPException: If session manager is not initialized
    """
    global _session_manager
    if _session_manager is None:
        from autoflow.auth import SessionManager, SessionPolicy

        _session_manager = SessionManager(policy=SessionPolicy())
    return _session_manager


def require_auth(
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> None:
    """
    Require authentication for endpoint access.

    Args:
        authorization: Bearer token from Authorization header

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not authorization or not authorization.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = authorization.credentials
    manager = get_session_manager()

    if not manager.is_valid_session(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )


def get_current_user_id(
    authorization: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Get the current authenticated user ID from session token.

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        User ID of the authenticated user

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not authorization or not authorization.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = authorization.credentials
    manager = get_session_manager()

    if not manager.is_valid_session(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    session = manager.get_session(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )

    return session.user_id


# === Request/Response Models ===


class UserListItem(BaseModel):
    """
    User list item model.

    Attributes:
        id: Unique user identifier
        email: User's email address
        name: User's full display name
        status: Current account status
        sso_provider: SSO provider used for authentication
        is_superuser: Admin bypass flag
        created_at: Account creation timestamp
    """

    id: str
    email: str
    name: str
    status: str
    sso_provider: str
    is_superuser: bool
    created_at: str


class UserListResponse(BaseModel):
    """
    User list response model.

    Attributes:
        users: List of users
        total: Total number of users
        page: Current page number
        page_size: Number of users per page
    """

    users: list[UserListItem]
    total: int
    page: int
    page_size: int


class UserDetailResponse(BaseModel):
    """
    User detail response model.

    Attributes:
        id: Unique user identifier
        email: User's email address
        name: User's full display name
        status: Current account status
        sso_provider: SSO provider used for authentication
        sso_id: External ID from SSO provider
        is_superuser: Admin bypass flag
        created_at: Account creation timestamp
        updated_at: Last update timestamp
        last_login: Most recent successful login
        roles: List of role names assigned to user
    """

    id: str
    email: str
    name: str
    status: str
    sso_provider: str
    sso_id: Optional[str] = None
    is_superuser: bool
    created_at: str
    updated_at: str
    last_login: Optional[str] = None
    roles: list[str] = []


class CreateUserRequest(BaseModel):
    """
    Create user request model.

    Attributes:
        email: User's email address
        name: User's full display name
        password: User's password (for local auth)
        sso_provider: SSO provider (for SSO users)
        sso_id: External SSO ID (for SSO users)
        status: Initial account status
        is_superuser: Admin flag
    """

    email: str
    name: str = Field(..., min_length=1)
    password: Optional[str] = None
    sso_provider: str = "none"
    sso_id: Optional[str] = None
    status: str = "pending"
    is_superuser: bool = False


class CreateUserResponse(BaseModel):
    """
    Create user response model.

    Attributes:
        id: Newly created user ID
        email: User's email address
        name: User's full display name
        status: Account status
    """

    id: str
    email: str
    name: str
    status: str


class UpdateUserRequest(BaseModel):
    """
    Update user request model.

    Attributes:
        name: User's full display name
        status: Account status
        is_superuser: Admin flag
    """

    name: Optional[str] = None
    status: Optional[str] = None
    is_superuser: Optional[bool] = None


class UpdateUserResponse(BaseModel):
    """
    Update user response model.

    Attributes:
        id: Updated user ID
        email: User's email address
        name: User's full display name
        status: Account status
        updated_at: Update timestamp
    """

    id: str
    email: str
    name: str
    status: str
    updated_at: str


class DeleteUserResponse(BaseModel):
    """
    Delete user response model.

    Attributes:
        message: Confirmation message
    """

    message: str


class RoleListResponse(BaseModel):
    """
    Role list response model.

    Attributes:
        roles: List of role names
    """

    roles: list[str]


class AddRoleRequest(BaseModel):
    """
    Add role request model.

    Attributes:
        role: Name of the role to add
    """

    role: str


class AddRoleResponse(BaseModel):
    """
    Add role response model.

    Attributes:
        message: Confirmation message
        role: Name of the added role
    """

    message: str
    role: str


class RemoveRoleResponse(BaseModel):
    """
    Remove role response model.

    Attributes:
        message: Confirmation message
        role: Name of the removed role
    """

    message: str
    role: str


class ErrorResponse(BaseModel):
    """
    Error response model.

    Attributes:
        error: Error message
        detail: Detailed error information
    """

    error: str
    detail: Optional[str] = None


# === Endpoints ===


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Number of users per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    current_user_id: str = Depends(get_current_user_id),
) -> UserListResponse:
    """
    List all users in the system.

    Requires authentication. Supports pagination and filtering by status.
    Admin permissions may be required to view all users.

    Args:
        page: Page number (1-indexed)
        page_size: Number of users per page (max 100)
        status: Optional filter by user status
        search: Optional search term for email/name
        current_user_id: ID of the authenticated user

    Returns:
        UserListResponse with paginated user list

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/users?page=1&page_size=20&status=active
    """
    # TODO: Implement actual user listing from database
    # For now, return empty list to demonstrate the pattern
    # In production, you would:
    # 1. Query database with pagination
    # 2. Apply filters (status, search)
    # 3. Check permissions (admin vs self-view)
    # 4. Return paginated results

    logger.info(
        f"User {current_user_id} listing users: page={page}, page_size={page_size}, "
        f"status={status}, search={search}"
    )

    # Placeholder: Return empty list
    return UserListResponse(
        users=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "User not found"},
    },
)
async def get_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> UserDetailResponse:
    """
    Get detailed information about a specific user.

    Requires authentication. Users can view their own profile.
    Admin permissions required to view other users.

    Args:
        user_id: ID of the user to retrieve
        current_user_id: ID of the authenticated user

    Returns:
        UserDetailResponse with user details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or user not found

    Example:
        >>> GET /api/v1/users/user-123
    """
    # TODO: Implement actual user retrieval from database
    # For now, return placeholder response
    # In production, you would:
    # 1. Query database for user by ID
    # 2. Check permissions (admin or self-view)
    # 3. Return user details with roles

    logger.info(f"User {current_user_id} viewing user {user_id}")

    # Placeholder: Return mock user data
    if user_id == "user-123":
        return UserDetailResponse(
            id=user_id,
            email="user@example.com",
            name="Test User",
            status="active",
            sso_provider="none",
            sso_id=None,
            is_superuser=False,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            last_login=None,
            roles=[],
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"User '{user_id}' not found",
    )


@router.post(
    "",
    response_model=CreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        409: {"model": ErrorResponse, "description": "Email already exists"},
    },
)
async def create_user(
    request: CreateUserRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> CreateUserResponse:
    """
    Create a new user account.

    Requires admin permissions. Can create users with local authentication
    or SSO integration.

    Args:
        request: User creation request
        current_user_id: ID of the authenticated user

    Returns:
        CreateUserResponse with created user details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or invalid input

    Example:
        >>> POST /api/v1/users
        >>> {
        ...     "email": "newuser@example.com",
        ...     "name": "New User",
        ...     "password": "secret123",
        ...     "status": "active"
        ... }
    """
    # TODO: Implement actual user creation
    # For now, return placeholder response
    # In production, you would:
    # 1. Validate input (email format, password strength)
    # 2. Check admin permissions
    # 3. Check if email already exists
    # 4. Hash password (if local auth)
    # 5. Create user in database
    # 6. Assign default roles
    # 7. Log audit event

    logger.info(f"User {current_user_id} creating user: {request.email}")

    # Placeholder: Return mock response
    from uuid import uuid4

    new_user_id = str(uuid4())

    return CreateUserResponse(
        id=new_user_id,
        email=request.email,
        name=request.name,
        status=request.status,
    )


@router.put(
    "/{user_id}",
    response_model=UpdateUserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "User not found"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> UpdateUserResponse:
    """
    Update an existing user account.

    Requires authentication. Users can update their own name.
    Admin permissions required to update status or superuser flag.

    Args:
        user_id: ID of the user to update
        request: User update request
        current_user_id: ID of the authenticated user

    Returns:
        UpdateUserResponse with updated user details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or user not found

    Example:
        >>> PUT /api/v1/users/user-123
        >>> {
        ...     "name": "Updated Name",
        ...     "status": "active"
        ... }
    """
    # TODO: Implement actual user update
    # For now, return placeholder response
    # In production, you would:
    # 1. Check permissions (admin or self-update)
    # 2. Query user from database
    # 3. Update allowed fields
    # 4. Log audit event

    logger.info(f"User {current_user_id} updating user {user_id}")

    # Placeholder: Return mock response
    from datetime import datetime

    if user_id == "user-123":
        return UpdateUserResponse(
            id=user_id,
            email="user@example.com",
            name=request.name or "Test User",
            status=request.status or "active",
            updated_at=datetime.utcnow().isoformat(),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"User '{user_id}' not found",
    )


@router.delete(
    "/{user_id}",
    response_model=DeleteUserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "User not found"},
    },
)
async def delete_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> DeleteUserResponse:
    """
    Delete a user account.

    Requires admin permissions. This is a permanent deletion
    and cannot be undone.

    Args:
        user_id: ID of the user to delete
        current_user_id: ID of the authenticated user

    Returns:
        DeleteUserResponse with confirmation message

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or user not found

    Example:
        >>> DELETE /api/v1/users/user-123
    """
    # TODO: Implement actual user deletion
    # For now, return placeholder response
    # In production, you would:
    # 1. Check admin permissions
    # 2. Prevent self-deletion
    # 3. Delete user from database (cascade to roles)
    # 4. Revoke all sessions
    # 5. Log audit event

    logger.info(f"User {current_user_id} deleting user {user_id}")

    # Placeholder: Check for self-deletion
    if user_id == current_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    # Placeholder: Return mock response
    return DeleteUserResponse(message=f"User '{user_id}' deleted successfully")


@router.get(
    "/{user_id}/roles",
    response_model=RoleListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "User not found"},
    },
)
async def get_user_roles(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> RoleListResponse:
    """
    Get roles assigned to a user.

    Requires authentication. Users can view their own roles.
    Admin permissions required to view other users' roles.

    Args:
        user_id: ID of the user
        current_user_id: ID of the authenticated user

    Returns:
        RoleListResponse with list of role names

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or user not found

    Example:
        >>> GET /api/v1/users/user-123/roles
    """
    # TODO: Implement actual role retrieval
    # For now, return placeholder response
    # In production, you would:
    # 1. Check permissions (admin or self-view)
    # 2. Query user roles from database
    # 3. Return role list

    logger.info(f"User {current_user_id} viewing roles for user {user_id}")

    # Placeholder: Return mock data
    if user_id == "user-123":
        return RoleListResponse(roles=[])

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"User '{user_id}' not found",
    )


@router.post(
    "/{user_id}/roles",
    response_model=AddRoleResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "User or role not found"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def add_user_role(
    user_id: str,
    request: AddRoleRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> AddRoleResponse:
    """
    Add a role to a user.

    Requires admin permissions.

    Args:
        user_id: ID of the user
        request: Role addition request
        current_user_id: ID of the authenticated user

    Returns:
        AddRoleResponse with confirmation message

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or not found

    Example:
        >>> POST /api/v1/users/user-123/roles
        >>> {"role": "developer"}
    """
    # TODO: Implement actual role assignment
    # For now, return placeholder response
    # In production, you would:
    # 1. Check admin permissions
    # 2. Query user and role from database
    # 3. Add role to user
    # 4. Log audit event

    logger.info(
        f"User {current_user_id} adding role '{request.role}' to user {user_id}"
    )

    # Placeholder: Return mock response
    return AddRoleResponse(
        message=f"Role '{request.role}' added to user '{user_id}'",
        role=request.role,
    )


@router.delete(
    "/{user_id}/roles/{role_name}",
    response_model=RemoveRoleResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "User or role not found"},
    },
)
async def remove_user_role(
    user_id: str,
    role_name: str,
    current_user_id: str = Depends(get_current_user_id),
) -> RemoveRoleResponse:
    """
    Remove a role from a user.

    Requires admin permissions.

    Args:
        user_id: ID of the user
        role_name: Name of the role to remove
        current_user_id: ID of the authenticated user

    Returns:
        RemoveRoleResponse with confirmation message

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or not found

    Example:
        >>> DELETE /api/v1/users/user-123/roles/developer
    """
    # TODO: Implement actual role removal
    # For now, return placeholder response
    # In production, you would:
    # 1. Check admin permissions
    # 2. Query user and role from database
    # 3. Remove role from user
    # 4. Log audit event

    logger.info(
        f"User {current_user_id} removing role '{role_name}' from user {user_id}"
    )

    # Placeholder: Return mock response
    return RemoveRoleResponse(
        message=f"Role '{role_name}' removed from user '{user_id}'",
        role=role_name,
    )
