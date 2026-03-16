"""
Autoflow Issue Client Base Module

Provides the abstract base class and common types for issue tracker clients.
All issue tracker implementations (GitHub, GitLab, Linear) inherit from
IssueClient and implement its abstract methods.

Usage:
    from autoflow.intake.client import IssueClient, IssueClientConfig, IssueResult

    class MyIssueClient(IssueClient):
        async def fetch_issue(self, issue_id, config):
            # Implementation
            pass
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class IssueSourceType(str, Enum):
    """
    Supported issue tracker sources.

    - GITHUB: GitHub Issues
    - GITLAB: GitLab Issues
    - LINEAR: Linear
    - JIRA: Atlassian JIRA (future)
    - GENERIC: Generic webhook source (future)
    """

    GITHUB = "github"
    GITLAB = "gitlab"
    LINEAR = "linear"
    JIRA = "jira"
    GENERIC = "generic"


class IssueClientConfig(BaseModel):
    """
    Configuration for an issue tracker client.

    Contains all settings needed to connect to and interact with
    an issue tracker API, including credentials, timeouts, and
    behavior options.

    Attributes:
        source_type: The type of issue source (github, gitlab, linear)
        base_url: API base URL (auto-detected if not provided)
        token: Authentication token (PAT, OAuth, API key)
        timeout_seconds: Request timeout
        retry_attempts: Number of retry attempts for failed requests
        retry_delay_seconds: Delay between retry attempts
        webhook_secret: Secret for webhook signature verification
        repository: Repository identifier (e.g., "owner/repo" for GitHub)
        metadata: Additional configuration metadata
    """

    source_type: IssueSourceType
    base_url: Optional[str] = None
    token: Optional[str] = None
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    webhook_secret: Optional[str] = None
    repository: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def headers(self) -> dict[str, str]:
        """
        Build standard HTTP headers for API requests.

        Returns:
            Dictionary of headers including authentication
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Autoflow/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


class IssueStatus(str, Enum):
    """Status of an issue."""

    BACKLOG = "backlog"
    TODO = "todo"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    MERGED = "merged"
    CANCELLED = "cancelled"


class IssuePriority(str, Enum):
    """Priority levels for issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class IssueResult(BaseModel):
    """
    Result of an issue API operation.

    Contains the response data, status, and metadata from API calls.
    All client methods must return an IssueResult.

    Attributes:
        success: Whether the operation succeeded
        data: Response data (issue object, list, etc.)
        error: Error message if operation failed
        status_code: HTTP status code
        rate_limit_remaining: Remaining rate limit (if available)
        raw_response: Raw response text
        metadata: Additional result metadata
    """

    success: bool
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    rate_limit_remaining: Optional[int] = None
    raw_response: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_success(
        cls,
        data: dict[str, Any],
        status_code: int = 200,
        rate_limit_remaining: Optional[int] = None,
        raw_response: Optional[str] = None,
    ) -> IssueResult:
        """
        Create a successful result.

        Args:
            data: Response data
            status_code: HTTP status code
            rate_limit_remaining: Remaining rate limit
            raw_response: Raw response text

        Returns:
            IssueResult with success=True
        """
        return cls(
            success=True,
            data=data,
            status_code=status_code,
            rate_limit_remaining=rate_limit_remaining,
            raw_response=raw_response,
        )

    @classmethod
    def from_error(
        cls,
        error: str,
        status_code: Optional[int] = None,
        raw_response: Optional[str] = None,
    ) -> IssueResult:
        """
        Create an error result.

        Args:
            error: Error message
            status_code: HTTP status code
            raw_response: Raw response text

        Returns:
            IssueResult with success=False
        """
        return cls(
            success=False,
            error=error,
            status_code=status_code,
            raw_response=raw_response,
        )


class IssueClient(ABC):
    """
    Abstract base class for issue tracker clients.

    Each client wraps a specific issue tracker API (GitHub, GitLab, Linear)
    and provides a unified interface for:
    - Fetching issues
    - Creating comments
    - Updating issue status
    - Listing issues
    - Webhook verification

    All methods are async for non-blocking parallel execution.

    Subclasses must implement:
    - fetch_issue(): Retrieve a single issue
    - list_issues(): List issues with filters
    - create_comment(): Add a comment to an issue
    - update_status(): Change issue status
    - verify_webhook(): Verify webhook signature

    Example:
        >>> class GitHubClient(IssueClient):
        ...     async def fetch_issue(self, issue_id, config):
        ...         # Call GitHub API
        ...         pass
        ...
        ...     async def list_issues(self, config, **filters):
        ...         # List GitHub issues
        ...         pass
    """

    @abstractmethod
    async def fetch_issue(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch a single issue by ID.

        Retrieves complete issue data including comments, labels,
        and metadata from the issue tracker.

        Args:
            issue_id: The issue identifier (format varies by source)
            config: Client configuration

        Returns:
            IssueResult with issue data in `data` field

        Example:
            >>> client = GitHubClient()
            >>> result = await client.fetch_issue(
            ...     issue_id="123",
            ...     config=IssueClientConfig(source_type=IssueSourceType.GITHUB)
            ... )
            >>> if result.success:
            ...     issue = result.data
        """
        pass

    @abstractmethod
    async def list_issues(
        self,
        config: IssueClientConfig,
        **filters: Any,
    ) -> IssueResult:
        """
        List issues with optional filters.

        Retrieves multiple issues matching the given filters.
        Common filters include status, labels, assignee, etc.

        Args:
            config: Client configuration
            **filters: Filter criteria (source-specific)

        Returns:
            IssueResult with list of issues in `data` field

        Example:
            >>> result = await client.list_issues(
            ...     config=config,
            ...     state="open",
            ...     labels=["bug", "critical"]
            ... )
        """
        pass

    @abstractmethod
    async def create_comment(
        self,
        issue_id: str,
        comment: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Create a comment on an issue.

        Adds a new comment to the specified issue.

        Args:
            issue_id: The issue identifier
            comment: Comment text (markdown supported)
            config: Client configuration

        Returns:
            IssueResult with created comment data

        Example:
            >>> result = await client.create_comment(
            ...     issue_id="123",
            ...     comment="Fixed in v2.0.0",
            ...     config=config
            ... )
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        issue_id: str,
        status: IssueStatus,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Update the status of an issue.

        Changes the issue's status (open, closed, in_progress, etc.)

        Args:
            issue_id: The issue identifier
            status: New status
            config: Client configuration

        Returns:
            IssueResult with updated issue data

        Example:
            >>> result = await client.update_status(
            ...     issue_id="123",
            ...     status=IssueStatus.CLOSED,
            ...     config=config
            ... )
        """
        pass

    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        config: IssueClientConfig,
    ) -> bool:
        """
        Verify a webhook signature.

        Validates that the webhook payload was signed by the
        expected source using the configured secret.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from request headers
            config: Client configuration with webhook_secret

        Returns:
            True if signature is valid, False otherwise

        Example:
            >>> is_valid = await client.verify_webhook(
            ...     payload=request.body,
            ...     signature=request.headers["X-Hub-Signature-256"],
            ...     config=config
            ... )
        """
        pass

    @property
    def source_type(self) -> IssueSourceType:
        """
        Return the source type for this client.

        Default implementation uses the class name to infer type.
        Subclasses can override for custom naming.

        Returns:
            IssueSourceType enum value

        Example:
            >>> GitHubClient().source_type
            IssueSourceType.GITHUB
        """
        class_name = self.__class__.__name__
        if class_name.endswith("Client"):
            name = class_name[:-6].lower()
        else:
            name = class_name.lower()

        # Map common class names to source types
        type_map = {
            "github": IssueSourceType.GITHUB,
            "gitlab": IssueSourceType.GITLAB,
            "linear": IssueSourceType.LINEAR,
            "jira": IssueSourceType.JIRA,
        }

        return type_map.get(name, IssueSourceType.GENERIC)

    async def check_health(self, config: IssueClientConfig) -> bool:
        """
        Check if the issue tracker API is accessible.

        Default implementation makes a simple authenticated request
        to verify connectivity. Subclasses can override for more
        sophisticated health checks.

        Args:
            config: Client configuration

        Returns:
            True if API is accessible and authentication works

        Example:
            >>> is_healthy = await client.check_health(config=config)
        """
        try:
            result = await self.list_issues(config, limit=1)
            return result.success
        except Exception:
            return False

    async def get_rate_limit(
        self,
        config: IssueClientConfig,
    ) -> Optional[dict[str, Any]]:
        """
        Get current rate limit status.

        Returns rate limit information if available from the API.
        Not all sources provide rate limit data.

        Args:
            config: Client configuration

        Returns:
            Dict with 'remaining', 'limit', 'reset' fields, or None

        Example:
            >>> rate_limit = await client.get_rate_limit(config=config)
            >>> if rate_limit:
            ...     print(f"{rate_limit['remaining']} requests remaining")
        """
        # Default: not implemented
        return None

    def __repr__(self) -> str:
        """Return string representation of the client."""
        return f"{self.__class__.__name__}(source_type={self.source_type.value})"


async def make_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    data: Optional[dict[str, Any]] = None,
    timeout: int = 30,
) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[int]]:
    """
    Make an async HTTP request.

    Utility function for making HTTP requests with proper error handling.
    Uses httpx if available, falls back to aiohttp.

    Args:
        url: Request URL
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        headers: Request headers
        data: Request body data
        timeout: Request timeout in seconds

    Returns:
        Tuple of (response_data, error_message, status_code)

    Example:
        >>> data, error, status = await make_http_request(
        ...     url="https://api.github.com/repos/owner/repo/issues/123",
        ...     headers={"Authorization": "Bearer token"}
        ... )
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers or {},
                json=data if data else None,
            )

            try:
                response_data = response.json()
            except Exception:
                response_data = {"raw": response.text}

            if response.status_code >= 400:
                error_msg = response_data.get("message", f"HTTP {response.status_code}")
                return None, error_msg, response.status_code

            return response_data, None, response.status_code

    except ImportError:
        # Fallback to asyncio + urllib if httpx not available
        import asyncio
        import json
        import urllib.request

        def sync_request() -> tuple[
            Optional[dict[str, Any]], Optional[str], Optional[int]
        ]:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode() if data else None,
                headers=headers or {},
                method=method,
            )

            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    response_data = json.loads(resp.read().decode())
                    return response_data, None, resp.status
            except urllib.error.HTTPError as e:
                error_data = json.loads(e.read().decode())
                return None, error_data.get("message", str(e)), e.code
            except Exception as e:
                return None, str(e), None

        return await asyncio.get_event_loop().run_in_executor(None, sync_request)
    except Exception as e:
        return None, str(e), None
