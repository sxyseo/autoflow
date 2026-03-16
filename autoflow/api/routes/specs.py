"""
Autoflow Specs Management API Routes

Provides endpoints for managing specification documents.
Supports spec CRUD operations with RBAC authorization.
Integrates with the state management for persistent storage.

Usage:
    from fastapi import FastAPI
    from autoflow.api.routes.specs import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/specs", tags=["Specifications"])
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from autoflow.auth import SessionManager
from autoflow.core.state import Spec

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


class SpecListItem(BaseModel):
    """
    Spec list item model.

    Attributes:
        id: Unique spec identifier
        title: Spec title
        version: Spec version
        author: Spec author
        created_at: Spec creation timestamp
        updated_at: Last update timestamp
        tags: List of tags associated with spec
    """

    id: str
    title: str
    version: str
    author: Optional[str] = None
    created_at: str
    updated_at: str
    tags: list[str] = []


class SpecListResponse(BaseModel):
    """
    Spec list response model.

    Attributes:
        specs: List of specs
        total: Total number of specs
    """

    specs: list[SpecListItem]
    total: int


class SpecDetailResponse(BaseModel):
    """
    Spec detail response model.

    Attributes:
        id: Unique spec identifier
        title: Spec title
        content: Spec content
        version: Spec version
        author: Spec author
        created_at: Spec creation timestamp
        updated_at: Last update timestamp
        tags: List of tags associated with spec
        metadata: Additional metadata
    """

    id: str
    title: str
    content: str
    version: str
    author: Optional[str] = None
    created_at: str
    updated_at: str
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class CreateSpecRequest(BaseModel):
    """
    Create spec request model.

    Attributes:
        id: Unique spec identifier
        title: Spec title
        content: Spec content
        version: Spec version
        tags: List of tags to associate with spec
        metadata: Additional metadata
    """

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    version: str = "1.0"
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class CreateSpecResponse(BaseModel):
    """
    Create spec response model.

    Attributes:
        id: Newly created spec ID
        title: Spec title
        version: Spec version
    """

    id: str
    title: str
    version: str


class UpdateSpecRequest(BaseModel):
    """
    Update spec request model.

    Attributes:
        title: Updated spec title
        content: Updated spec content
        version: Updated spec version
        tags: Updated list of tags
        metadata: Updated metadata
    """

    title: Optional[str] = None
    content: Optional[str] = None
    version: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class UpdateSpecResponse(BaseModel):
    """
    Update spec response model.

    Attributes:
        id: Updated spec ID
        title: Updated spec title
        version: Updated spec version
        updated_at: Update timestamp
    """

    id: str
    title: str
    version: str
    updated_at: str


class DeleteSpecResponse(BaseModel):
    """
    Delete spec response model.

    Attributes:
        message: Confirmation message
    """

    message: str


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
    response_model=SpecListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def list_specs(
    tags: Optional[list[str]] = Query(None, description="Filter by tags"),
    current_user_id: str = Depends(get_current_user_id),
) -> SpecListResponse:
    """
    List all specification documents.

    Requires authentication. Supports filtering by tags.
    Users with read permissions can view specs.

    Args:
        tags: Optional list of tags to filter by
        current_user_id: ID of the authenticated user

    Returns:
        SpecListResponse with list of specs

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/specs?tags=backend&tags=api
    """
    # TODO: Implement actual spec listing from state/database
    # For now, return empty list to demonstrate the pattern
    # In production, you would:
    # 1. Check user permissions (specs:read)
    # 2. Query state manager or database for specs
    # 3. Apply filters (tags)
    # 4. Return paginated results

    logger.info(f"User {current_user_id} listing specs: tags={tags}")

    # Placeholder: Return empty list
    return SpecListResponse(
        specs=[],
        total=0,
    )


@router.get(
    "/{spec_id}",
    response_model=SpecDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Spec not found"},
    },
)
async def get_spec(
    spec_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> SpecDetailResponse:
    """
    Get detailed information about a specific specification.

    Requires authentication. Users with read permissions can view specs.

    Args:
        spec_id: ID of the spec to retrieve
        current_user_id: ID of the authenticated user

    Returns:
        SpecDetailResponse with spec details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or spec not found

    Example:
        >>> GET /api/v1/specs/spec-123
    """
    # TODO: Implement actual spec retrieval from state/database
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (specs:read)
    # 2. Query state manager or database for spec by ID
    # 3. Return spec details

    logger.info(f"User {current_user_id} viewing spec {spec_id}")

    # Placeholder: Return mock spec data
    if spec_id == "spec-123":
        return SpecDetailResponse(
            id=spec_id,
            title="Example Specification",
            content="# Example Spec\n\nThis is an example specification document.",
            version="1.0",
            author="user@example.com",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            tags=["example", "backend"],
            metadata={},
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Spec '{spec_id}' not found",
    )


@router.post(
    "",
    response_model=CreateSpecResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        409: {"model": ErrorResponse, "description": "Spec already exists"},
    },
)
async def create_spec(
    request: CreateSpecRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> CreateSpecResponse:
    """
    Create a new specification document.

    Requires authentication. Users with write permissions can create specs.

    Args:
        request: Spec creation request
        current_user_id: ID of the authenticated user

    Returns:
        CreateSpecResponse with created spec details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or invalid input

    Example:
        >>> POST /api/v1/specs
        >>> {
        ...     "id": "spec-backend-api",
        ...     "title": "Backend API Specification",
        ...     "content": "# Backend API\\n\\nSpecification details...",
        ...     "tags": ["backend", "api"]
        ... }
    """
    # TODO: Implement actual spec creation
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (specs:write)
    # 2. Validate input (ID format, content)
    # 3. Check if spec ID already exists
    # 4. Create spec in state manager or database
    # 5. Log audit event

    logger.info(f"User {current_user_id} creating spec: {request.id}")

    # Placeholder: Return mock response
    return CreateSpecResponse(
        id=request.id,
        title=request.title,
        version=request.version,
    )


@router.put(
    "/{spec_id}",
    response_model=UpdateSpecResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Spec not found"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def update_spec(
    spec_id: str,
    request: UpdateSpecRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> UpdateSpecResponse:
    """
    Update an existing specification document.

    Requires authentication. Users with write permissions can update specs.

    Args:
        spec_id: ID of the spec to update
        request: Spec update request
        current_user_id: ID of the authenticated user

    Returns:
        UpdateSpecResponse with updated spec details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or spec not found

    Example:
        >>> PUT /api/v1/specs/spec-123
        >>> {
        ...     "title": "Updated Title",
        ...     "content": "# Updated Content"
        ... }
    """
    # TODO: Implement actual spec update
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (specs:write)
    # 2. Query spec from state manager or database
    # 3. Update allowed fields
    # 4. Log audit event

    logger.info(f"User {current_user_id} updating spec {spec_id}")

    # Placeholder: Return mock response
    from datetime import datetime

    if spec_id == "spec-123":
        return UpdateSpecResponse(
            id=spec_id,
            title=request.title or "Example Specification",
            version=request.version or "1.0",
            updated_at=datetime.utcnow().isoformat(),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Spec '{spec_id}' not found",
    )


@router.delete(
    "/{spec_id}",
    response_model=DeleteSpecResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Spec not found"},
    },
)
async def delete_spec(
    spec_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> DeleteSpecResponse:
    """
    Delete a specification document.

    Requires authentication. Users with delete permissions can delete specs.
    This is a permanent deletion and cannot be undone.

    Args:
        spec_id: ID of the spec to delete
        current_user_id: ID of the authenticated user

    Returns:
        DeleteSpecResponse with confirmation message

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or spec not found

    Example:
        >>> DELETE /api/v1/specs/spec-123
    """
    # TODO: Implement actual spec deletion
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (specs:delete)
    # 2. Query spec from state manager or database
    # 3. Delete spec
    # 4. Log audit event

    logger.info(f"User {current_user_id} deleting spec {spec_id}")

    # Placeholder: Return mock response
    return DeleteSpecResponse(message=f"Spec '{spec_id}' deleted successfully")
