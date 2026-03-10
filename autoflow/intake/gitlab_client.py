"""
Autoflow GitLab Client Module

Provides async GitLab API client for issue operations.
Supports fetching, creating, and updating GitLab issues and comments,
as well as webhook signature verification.

Usage:
    from autoflow.intake.gitlab_client import GitLabClient
    from autoflow.intake.client import IssueClientConfig, IssueSourceType

    config = IssueClientConfig(
        source_type=IssueSourceType.GITLAB,
        token="glpat-xxx",
        repository="owner/repo"
    )
    client = GitLabClient()
    result = await client.fetch_issue("123", config)
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

from autoflow.intake.client import (
    IssueClient,
    IssueClientConfig,
    IssueResult,
    IssueStatus,
    make_http_request,
)


class GitLabClient(IssueClient):
    """
    GitLab Issues API client.

    Implements GitLab REST API v4 for issue operations including:
    - Fetching single issues with comments and labels
    - Listing issues with filters (state, labels, assignee, etc.)
    - Creating comments
    - Updating issue state (opened/closed)
    - Webhook signature verification
    - Rate limit tracking

    GitLab API docs: https://docs.gitlab.com/ee/api/issues.html

    Example:
        >>> config = IssueClientConfig(
        ...     source_type=IssueSourceType.GITLAB,
        ...     token="glpat-xxx",
        ...     repository="owner/repo"
        ... )
        >>> client = GitLabClient()
        >>> result = await client.fetch_issue("123", config)
        >>> if result.success:
        ...     issue = result.data
    """

    # GitLab API constants
    DEFAULT_BASE_URL = "https://gitlab.com/api/v4"
    API_VERSION = "v4"

    def _get_base_url(self, config: IssueClientConfig) -> str:
        """
        Get the API base URL for GitLab.

        Args:
            config: Client configuration

        Returns:
            Base URL for GitLab API
        """
        return config.base_url or self.DEFAULT_BASE_URL

    def _get_headers(self, config: IssueClientConfig) -> dict[str, str]:
        """
        Build HTTP headers for GitLab API requests.

        Args:
            config: Client configuration

        Returns:
            Dictionary of headers including auth and API version
        """
        headers = {
            "Accept": "application/json",
            "User-Agent": "Autoflow/1.0",
        }
        if config.token:
            # GitLab supports both PRIVATE-TOKEN and Bearer token
            headers["PRIVATE-TOKEN"] = config.token
        return headers

    def _encode_project_path(self, project_path: str) -> str:
        """
        Encode a project path for use in GitLab API URLs.

        GitLab API requires URL-encoded project paths (e.g., "owner/repo" becomes "owner%2Frepo").

        Args:
            project_path: Project path (e.g., "owner/repo")

        Returns:
            URL-encoded project path

        Example:
            >>> client._encode_project_path("owner/repo")
            'owner%2Frepo'
        """
        return project_path.replace("/", "%2F")

    async def fetch_issue(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch a single GitLab issue by IID.

        Retrieves complete issue data including comments, labels,
        and metadata from GitLab's REST API.

        Args:
            issue_id: The issue IID (internal ID, as string, e.g., "123")
            config: Client configuration with repository

        Returns:
            IssueResult with issue data in `data` field

        Raises:
            ValueError: If repository is not configured
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues/{issue_id}"
        headers = self._get_headers(config)

        data, error, status = await make_http_request(
            url=url,
            method="GET",
            headers=headers,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        # Extract rate limit from headers if available
        rate_limit = None  # Would need to extract from response headers

        return IssueResult.from_success(
            data=data,
            status_code=status,
            rate_limit_remaining=rate_limit,
        )

    async def list_issues(
        self,
        config: IssueClientConfig,
        **filters: Any,
    ) -> IssueResult:
        """
        List GitLab issues with optional filters.

        Supports GitLab's issue filtering API including:
        - state: opened, closed, or all
        - labels: Comma-separated label names
        - assignee: Username or assignee ID
        - author: Username or author ID
        - milestone: Milestone title or ID
        - order_by: created_at, updated_at, priority, due_date
        - sort: asc or desc
        - per_page: Results per page (max 100)
        - page: Page number
        - search: Search in title and description

        Args:
            config: Client configuration with repository
            **filters: GitLab API filter parameters

        Returns:
            IssueResult with list of issues in `data` field

        Example:
            >>> result = await client.list_issues(
            ...     config=config,
            ...     state="opened",
            ...     labels="bug,critical",
            ...     order_by="created_at",
            ...     sort="desc"
            ... )
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues"
        headers = self._get_headers(config)

        # Build query string from filters
        query_params = []
        for key, value in filters.items():
            if value is not None:
                query_params.append(f"{key}={str(value)}")

        if query_params:
            url = f"{url}?{'&'.join(query_params)}"

        data, error, status = await make_http_request(
            url=url,
            method="GET",
            headers=headers,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        # GitLab returns a list of issues
        return IssueResult.from_success(
            data={"issues": data},
            status_code=status,
        )

    async def create_comment(
        self,
        issue_id: str,
        comment: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Create a comment (note) on a GitLab issue.

        Creates a new note using GitLab's issue notes API.
        Markdown is supported in comment text.

        Args:
            issue_id: The issue IID (as string)
            comment: Comment text (markdown supported)
            config: Client configuration with repository

        Returns:
            IssueResult with created comment data

        Example:
            >>> result = await client.create_comment(
            ...     issue_id="123",
            ...     comment="Fixed in v2.0.0. See MR !456 for details.",
            ...     config=config
            ... )
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues/{issue_id}/notes"
        headers = self._get_headers(config)

        payload = {"body": comment}

        data, error, status = await make_http_request(
            url=url,
            method="POST",
            headers=headers,
            data=payload,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        return IssueResult.from_success(
            data=data,
            status_code=status,
        )

    async def update_status(
        self,
        issue_id: str,
        status: IssueStatus,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Update the status of a GitLab issue.

        Changes the issue's state. GitLab supports "opened" and "closed"
        states, so we map other statuses appropriately:
        - OPEN, IN_PROGRESS -> "opened"
        - CLOSED, MERGED, CANCELLED -> "closed"

        Args:
            issue_id: The issue IID (as string)
            status: New status from IssueStatus enum
            config: Client configuration with repository

        Returns:
            IssueResult with updated issue data

        Note:
            GitLab issues do not support "in_progress" state natively.
            Consider using labels or boards to indicate progress.
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        # Map IssueStatus to GitLab's state values
        if status in (IssueStatus.OPEN, IssueStatus.IN_PROGRESS):
            gitlab_state = "opened"
        elif status in (IssueStatus.CLOSED, IssueStatus.MERGED, IssueStatus.CANCELLED):
            gitlab_state = "closed"
        else:
            return IssueResult.from_error(
                f"Unsupported status for GitLab: {status}. "
                f"GitLab only supports opened/closed states.",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues/{issue_id}"
        headers = self._get_headers(config)

        payload = {"state_event": gitlab_state}

        data, error, status_code = await make_http_request(
            url=url,
            method="PUT",
            headers=headers,
            data=payload,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status_code)

        return IssueResult.from_success(
            data=data,
            status_code=status_code,
        )

    async def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        config: IssueClientConfig,
    ) -> bool:
        """
        Verify a GitLab webhook signature.

        GitLab webhooks use a simple token verification mechanism.
        The token is provided in the `X-Gitlab-Token` header
        and should match the configured webhook secret.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from X-Gitlab-Token header
            config: Client configuration with webhook_secret

        Returns:
            True if signature is valid, False otherwise

        Example:
            >>> is_valid = await client.verify_webhook(
            ...     payload=request.body,
            ...     signature=request.headers["X-Gitlab-Token"],
            ...     config=config
            ... )

        Security:
            Always verify webhook signatures to ensure requests
            originated from GitLab and not a malicious actor.

        Note:
            GitLab's webhook verification uses a simple token comparison,
            not a cryptographic signature like GitHub's HMAC.
        """
        if not config.webhook_secret:
            # No secret configured, cannot verify
            return False

        if not signature:
            return False

        # GitLab uses simple token comparison
        # The signature should match the webhook_secret exactly
        return hmac.compare_digest(signature, config.webhook_secret)

    async def get_rate_limit(
        self,
        config: IssueClientConfig,
    ) -> Optional[dict[str, Any]]:
        """
        Get current GitLab API rate limit status.

        GitLab provides rate limit information through specific headers
        in API responses (RateLimit-Remaining, RateLimit-Limit, etc.).

        Args:
            config: Client configuration

        Returns:
            Dict with rate limit info:
            - limit: Total requests allowed per period
            - remaining: Remaining requests this period
            - reset: Unix timestamp when limit resets (if available)
            - used: Requests used this period (if available)

        Example:
            >>> rate_limit = await client.get_rate_limit(config=config)
            >>> if rate_limit:
            ...     print(f"{rate_limit['remaining']} of {rate_limit['limit']} remaining")
        """
        # GitLab rate limits are returned in response headers, not a dedicated endpoint
        # We can't get them without making an actual API request
        # This is a placeholder - in practice, you'd extract these from responses
        return None

    async def fetch_issue_comments(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch all comments (notes) for a GitLab issue.

        Retrieves all notes associated with an issue in chronological order.

        Args:
            issue_id: The issue IID (as string)
            config: Client configuration with repository

        Returns:
            IssueResult with list of comments in `data` field

        Example:
            >>> result = await client.fetch_issue_comments("123", config)
            >>> if result.success:
            ...     comments = result.data.get("comments", [])
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues/{issue_id}/notes"
        headers = self._get_headers(config)

        data, error, status = await make_http_request(
            url=url,
            method="GET",
            headers=headers,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        return IssueResult.from_success(
            data={"comments": data},
            status_code=status,
        )

    async def add_labels(
        self,
        issue_id: str,
        labels: list[str],
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Add labels to a GitLab issue.

        Adds one or more labels to an issue.

        Args:
            issue_id: The issue IID (as string)
            labels: List of label names to add
            config: Client configuration with repository

        Returns:
            IssueResult with updated issue data

        Example:
            >>> result = await client.add_labels(
            ...     issue_id="123",
            ...     labels=["bug", "critical", "triaged"],
            ...     config=config
            ... )
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues/{issue_id}"
        headers = self._get_headers(config)

        # GitLab uses comma-separated labels string
        payload = {"add_labels": ",".join(labels)}

        data, error, status = await make_http_request(
            url=url,
            method="PUT",
            headers=headers,
            data=payload,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        return IssueResult.from_success(
            data=data,
            status_code=status,
        )

    async def set_labels(
        self,
        issue_id: str,
        labels: list[str],
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Replace all labels on a GitLab issue.

        Replaces all existing labels with the provided list.
        Use this to completely reset an issue's labels.

        Args:
            issue_id: The issue IID (as string)
            labels: List of label names to set
            config: Client configuration with repository

        Returns:
            IssueResult with updated issue data
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        encoded_project = self._encode_project_path(config.repository)
        url = f"{base_url}/projects/{encoded_project}/issues/{issue_id}"
        headers = self._get_headers(config)

        # GitLab uses comma-separated labels string
        payload = {"labels": ",".join(labels)}

        data, error, status = await make_http_request(
            url=url,
            method="PUT",
            headers=headers,
            data=payload,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        return IssueResult.from_success(
            data=data,
            status_code=status,
        )
