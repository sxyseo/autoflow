"""
Autoflow GitHub Client Module

Provides async GitHub API client for issue operations.
Supports fetching, creating, and updating GitHub issues and comments,
as well as webhook signature verification.

Usage:
    from autoflow.intake.github_client import GitHubClient
    from autoflow.intake.client import IssueClientConfig, IssueSourceType

    config = IssueClientConfig(
        source_type=IssueSourceType.GITHUB,
        token="ghp_xxx",
        repository="owner/repo"
    )
    client = GitHubClient()
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


class GitHubClient(IssueClient):
    """
    GitHub Issues API client.

    Implements GitHub REST API v3 for issue operations including:
    - Fetching single issues with comments and labels
    - Listing issues with filters (state, labels, assignee, etc.)
    - Creating comments
    - Updating issue state (open/closed)
    - Webhook signature verification
    - Rate limit tracking

    GitHub API docs: https://docs.github.com/en/rest/issues

    Example:
        >>> config = IssueClientConfig(
        ...     source_type=IssueSourceType.GITHUB,
        ...     token="ghp_xxx",
        ...     repository="owner/repo"
        ... )
        >>> client = GitHubClient()
        >>> result = await client.fetch_issue("123", config)
        >>> if result.success:
        ...     issue = result.data
    """

    # GitHub API constants
    DEFAULT_BASE_URL = "https://api.github.com"
    API_VERSION = "v3"

    def _get_base_url(self, config: IssueClientConfig) -> str:
        """
        Get the API base URL for GitHub.

        Args:
            config: Client configuration

        Returns:
            Base URL for GitHub API
        """
        return config.base_url or self.DEFAULT_BASE_URL

    def _get_headers(self, config: IssueClientConfig) -> dict[str, str]:
        """
        Build HTTP headers for GitHub API requests.

        Args:
            config: Client configuration

        Returns:
            Dictionary of headers including auth and API version
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Autoflow/1.0",
            "X-GitHub-Api-Version": self.API_VERSION,
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        return headers

    async def fetch_issue(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch a single GitHub issue by number.

        Retrieves complete issue data including comments, labels,
        and metadata from GitHub's REST API.

        Args:
            issue_id: The issue number (as string, e.g., "123")
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
        url = f"{base_url}/repos/{config.repository}/issues/{issue_id}"
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
        List GitHub issues with optional filters.

        Supports GitHub's issue filtering API including:
        - state: open, closed, or all
        - labels: Comma-separated label names
        - assignee: Username, "none", or "*"
        - creator: Username
        - mentioned: Username
        - milestone: Milestone number or "none" or "*"
        - sort: created, updated, comments
        - direction: asc or desc
        - since: ISO 8601 timestamp
        - per_page: Results per page (max 100)
        - page: Page number

        Args:
            config: Client configuration with repository
            **filters: GitHub API filter parameters

        Returns:
            IssueResult with list of issues in `data` field

        Example:
            >>> result = await client.list_issues(
            ...     config=config,
            ...     state="open",
            ...     labels="bug,critical",
            ...     sort="created",
            ...     direction="desc"
            ... )
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        url = f"{base_url}/repos/{config.repository}/issues"
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

        # GitHub returns a list of issues
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
        Create a comment on a GitHub issue.

        Creates a new comment using GitHub's issue comments API.
        Markdown is supported in comment text.

        Args:
            issue_id: The issue number (as string)
            comment: Comment text (markdown supported)
            config: Client configuration with repository

        Returns:
            IssueResult with created comment data

        Example:
            >>> result = await client.create_comment(
            ...     issue_id="123",
            ...     comment="Fixed in v2.0.0. See PR #456 for details.",
            ...     config=config
            ... )
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        url = f"{base_url}/repos/{config.repository}/issues/{issue_id}/comments"
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
        Update the status of a GitHub issue.

        Changes the issue's state. GitHub only supports "open" and "closed"
        states, so we map other statuses appropriately:
        - OPEN, IN_PROGRESS -> "open"
        - CLOSED, MERGED, CANCELLED -> "closed"

        Args:
            issue_id: The issue number (as string)
            status: New status from IssueStatus enum
            config: Client configuration with repository

        Returns:
            IssueResult with updated issue data

        Note:
            GitHub issues do not support "in_progress" state natively.
            Consider using labels or projects to indicate progress.
        """
        if not config.repository:
            return IssueResult.from_error(
                "Repository must be configured (format: owner/repo)",
                status_code=400,
            )

        # Map IssueStatus to GitHub's state values
        if status in (IssueStatus.OPEN, IssueStatus.IN_PROGRESS):
            github_state = "open"
        elif status in (IssueStatus.CLOSED, IssueStatus.MERGED, IssueStatus.CANCELLED):
            github_state = "closed"
        else:
            return IssueResult.from_error(
                f"Unsupported status for GitHub: {status}. "
                f"GitHub only supports open/closed states.",
                status_code=400,
            )

        base_url = self._get_base_url(config)
        url = f"{base_url}/repos/{config.repository}/issues/{issue_id}"
        headers = self._get_headers(config)

        payload = {"state": github_state}

        data, error, status_code = await make_http_request(
            url=url,
            method="PATCH",
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
        Verify a GitHub webhook signature.

        GitHub webhooks are signed using HMAC-SHA256 with the webhook secret.
        The signature is provided in the `X-Hub-Signature-256` header
        with format: `sha256=<hex_digest>`.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from X-Hub-Signature-256 header
            config: Client configuration with webhook_secret

        Returns:
            True if signature is valid, False otherwise

        Example:
            >>> is_valid = await client.verify_webhook(
            ...     payload=request.body,
            ...     signature=request.headers["X-Hub-Signature-256"],
            ...     config=config
            ... )

        Security:
            Always verify webhook signatures to ensure requests
            originated from GitHub and not a malicious actor.
        """
        if not config.webhook_secret:
            # No secret configured, cannot verify
            return False

        if not signature:
            return False

        # GitHub signature format: "sha256=<hex_signature>"
        if not signature.startswith("sha256="):
            return False

        # Extract the signature hash
        github_signature = signature[7:]  # Remove "sha256=" prefix

        # Compute HMAC-SHA256 of payload
        expected_signature = hmac.new(
            config.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(github_signature, expected_signature)

    async def get_rate_limit(
        self,
        config: IssueClientConfig,
    ) -> Optional[dict[str, Any]]:
        """
        Get current GitHub API rate limit status.

        Returns rate limit information from GitHub's rate limit endpoint.
        This provides detailed rate limit data for all API endpoints.

        Args:
            config: Client configuration

        Returns:
            Dict with rate limit info:
            - limit: Total requests allowed per hour
            - remaining: Remaining requests this hour
            - reset: Unix timestamp when limit resets
            - used: Requests used this hour

        Example:
            >>> rate_limit = await client.get_rate_limit(config=config)
            >>> if rate_limit:
            ...     print(f"{rate_limit['remaining']} of {rate_limit['limit']} remaining")
        """
        base_url = self._get_base_url(config)
        url = f"{base_url}/rate_limit"
        headers = self._get_headers(config)

        data, error, _ = await make_http_request(
            url=url,
            method="GET",
            headers=headers,
            timeout=config.timeout_seconds,
        )

        if error or not data:
            return None

        # Extract core API rate limit from response
        # GitHub returns: {"resources": {"core": {...}, "search": {...}, ...}}
        try:
            core_rate_limit = data.get("resources", {}).get("core", {})
            return {
                "limit": core_rate_limit.get("limit"),
                "remaining": core_rate_limit.get("remaining"),
                "reset": core_rate_limit.get("reset"),
                "used": core_rate_limit.get("used"),
            }
        except (AttributeError, KeyError):
            return None

    async def fetch_issue_comments(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch all comments for a GitHub issue.

        Retrieves all comments associated with an issue in chronological order.

        Args:
            issue_id: The issue number (as string)
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
        url = f"{base_url}/repos/{config.repository}/issues/{issue_id}/comments"
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
        Add labels to a GitHub issue.

        Adds one or more labels to an issue. Labels that don't exist
        will be created automatically.

        Args:
            issue_id: The issue number (as string)
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
        url = f"{base_url}/repos/{config.repository}/issues/{issue_id}/labels"
        headers = self._get_headers(config)

        payload = {"labels": labels}

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

    async def set_labels(
        self,
        issue_id: str,
        labels: list[str],
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Replace all labels on a GitHub issue.

        Replaces all existing labels with the provided list.
        Use this to completely reset an issue's labels.

        Args:
            issue_id: The issue number (as string)
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
        url = f"{base_url}/repos/{config.repository}/issues/{issue_id}"
        headers = self._get_headers(config)

        payload = {"labels": labels}

        data, error, status = await make_http_request(
            url=url,
            method="PATCH",
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
