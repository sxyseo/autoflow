"""
Autoflow Linear Client Module

Provides async Linear API client for issue operations.
Supports fetching, creating, and updating Linear issues and comments,
as well as webhook signature verification.

Usage:
    from autoflow.intake.linear_client import LinearClient
    from autoflow.intake.client import IssueClientConfig, IssueSourceType

    config = IssueClientConfig(
        source_type=IssueSourceType.LINEAR,
        token="lin_api_xxx",
        repository="workspace-key"
    )
    client = LinearClient()
    result = await client.fetch_issue("abc-123", config)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional

from autoflow.intake.client import (
    IssueClient,
    IssueClientConfig,
    IssueResult,
    IssueStatus,
    make_http_request,
)


class LinearClient(IssueClient):
    """
    Linear Issues API client.

    Implements Linear GraphQL API for issue operations including:
    - Fetching single issues with comments and labels
    - Listing issues with filters (state, labels, assignee, etc.)
    - Creating comments
    - Updating issue state
    - Webhook signature verification
    - Rate limit tracking

    Linear API docs: https://developers.linear.app/docs/graphql/api

    Example:
        >>> config = IssueClientConfig(
        ...     source_type=IssueSourceType.LINEAR,
        ...     token="lin_api_xxx",
        ...     repository="my-workspace"
        ... )
        >>> client = LinearClient()
        >>> result = await client.fetch_issue("LIN-123", config)
        >>> if result.success:
        ...     issue = result.data
    """

    # Linear API constants
    DEFAULT_BASE_URL = "https://api.linear.app/graphql"
    API_VERSION = "2024-02-28"

    # Linear state type mapping
    STATE_TYPE_MAPPING = {
        "backlog": IssueStatus.BACKLOG,
        "todo": IssueStatus.TODO,
        "in_progress": IssueStatus.IN_PROGRESS,
        "done": IssueStatus.CLOSED,
        "canceled": IssueStatus.CANCELLED,
        "cancelled": IssueStatus.CANCELLED,
    }

    # Reverse mapping for updating status
    STATUS_TO_STATE_TYPE = {
        IssueStatus.BACKLOG: "backlog",
        IssueStatus.TODO: "todo",
        IssueStatus.IN_PROGRESS: "in_progress",
        IssueStatus.CLOSED: "done",
        IssueStatus.CANCELLED: "canceled",
        IssueStatus.MERGED: "done",  # Linear doesn't have merged, map to done
    }

    def _get_base_url(self, config: IssueClientConfig) -> str:
        """
        Get the API base URL for Linear.

        Args:
            config: Client configuration

        Returns:
            Base URL for Linear GraphQL API
        """
        return config.base_url or self.DEFAULT_BASE_URL

    def _get_headers(self, config: IssueClientConfig) -> dict[str, str]:
        """
        Build HTTP headers for Linear API requests.

        Args:
            config: Client configuration

        Returns:
            Dictionary of headers including auth and API version
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Autoflow/1.0",
        }
        if config.token:
            headers["Authorization"] = config.token
        return headers

    async def _execute_query(
        self,
        query: str,
        variables: dict[str, Any],
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Execute a GraphQL query against Linear API.

        Args:
            query: GraphQL query string
            variables: GraphQL variables dict
            config: Client configuration

        Returns:
            IssueResult with query response data
        """
        url = self._get_base_url(config)
        headers = self._get_headers(config)

        payload = {
            "query": query,
            "variables": variables,
        }

        data, error, status = await make_http_request(
            url=url,
            method="POST",
            headers=headers,
            data=payload,
            timeout=config.timeout_seconds,
        )

        if error:
            return IssueResult.from_error(error, status_code=status)

        # Check for GraphQL errors
        if isinstance(data, dict) and "errors" in data:
            errors = data["errors"]
            error_messages = [err.get("message", str(err)) for err in errors]
            return IssueResult.from_error(
                "; ".join(error_messages),
                status_code=status,
            )

        return IssueResult.from_success(
            data=data,
            status_code=status,
        )

    async def fetch_issue(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch a single Linear issue by ID.

        Retrieves complete issue data including comments, labels,
        and metadata from Linear's GraphQL API.

        Args:
            issue_id: The issue identifier (e.g., "LIN-123" or UUID)
            config: Client configuration

        Returns:
            IssueResult with issue data in `data` field

        Example:
            >>> result = await client.fetch_issue("LIN-123", config)
            >>> if result.success:
            ...     issue = result.data["data"]["issue"]
        """
        # GraphQL query to fetch issue with all related data
        query = """
        query Issue($issueId: String!) {
            issue(id: $issueId) {
                id
                identifier
                title
                description
                state {
                    id
                    name
                    type
                    color
                }
                priority
                priorityLabel
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
                assignee {
                    id
                    name
                    email
                    avatarUrl
                }
                creator {
                    id
                    name
                    email
                }
                project {
                    id
                    name
                }
                team {
                    id
                    key
                    name
                }
                createdAt
                updatedAt
                dueDate
                url
                comments {
                    nodes {
                        id
                        body
                        user {
                            id
                            name
                            email
                        }
                        createdAt
                        updatedAt
                    }
                }
            }
        }
        """

        variables = {"issueId": issue_id}
        result = await self._execute_query(query, variables, config)

        if not result.success:
            return result

        # Extract issue data from GraphQL response
        issue_data = result.data.get("data", {}).get("issue")

        if not issue_data:
            return IssueResult.from_error(
                f"Issue not found: {issue_id}",
                status_code=404,
            )

        # Return the issue data wrapped in the expected format
        return IssueResult.from_success(
            data={"issue": issue_data},
            status_code=result.status_code,
        )

    async def list_issues(
        self,
        config: IssueClientConfig,
        **filters: Any,
    ) -> IssueResult:
        """
        List Linear issues with optional filters.

        Supports Linear's issue filtering including:
        - team: Team key or ID
        - state: State type (backlog, todo, in_progress, done, canceled)
        - labels: Label names
        - assignee: User ID
        - priority: Priority level
        - project: Project ID
        - first: Number of results (max 100)
        - after: Cursor for pagination

        Args:
            config: Client configuration
            **filters: Filter criteria for Linear query

        Returns:
            IssueResult with list of issues in `data` field

        Example:
            >>> result = await client.list_issues(
            ...     config=config,
            ...     team="MYT",
            ...     state="in_progress",
            ...     first=50
            ... )
        """
        # Build GraphQL query for listing issues
        query = """
        query Issues(
            $teamId: String = null,
            $stateId: String = null,
            $assigneeId: String = null,
            $projectId: String = null,
            $first: Int = 50,
            $after: String = null
        ) {
            issues(
                filter: {
                    team: { key: $teamId }
                    state: { id: $stateId }
                    assignee: { id: $assigneeId }
                    project: { id: $projectId }
                }
                first: $first
                after: $after
            ) {
                nodes {
                    id
                    identifier
                    title
                    description
                    state {
                        id
                        name
                        type
                    }
                    priority
                    priorityLabel
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                    assignee {
                        id
                        name
                        email
                    }
                    creator {
                        id
                        name
                    }
                    project {
                        id
                        name
                    }
                    team {
                        id
                        key
                        name
                    }
                    createdAt
                    updatedAt
                    dueDate
                    url
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """

        # Extract filters and build variables
        variables = {
            "teamId": filters.get("team"),
            "stateId": filters.get("state"),
            "assigneeId": filters.get("assignee"),
            "projectId": filters.get("project"),
            "first": filters.get("first", 50),
            "after": filters.get("after"),
        }

        # Remove None values
        variables = {k: v for k, v in variables.items() if v is not None}

        result = await self._execute_query(query, variables, config)

        if not result.success:
            return result

        # Extract issues from GraphQL response
        issues_data = result.data.get("data", {}).get("issues", {})
        issues = issues_data.get("nodes", [])
        page_info = issues_data.get("pageInfo", {})

        return IssueResult.from_success(
            data={
                "issues": issues,
                "pageInfo": page_info,
            },
            status_code=result.status_code,
        )

    async def create_comment(
        self,
        issue_id: str,
        comment: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Create a comment on a Linear issue.

        Creates a new comment using Linear's GraphQL mutation API.
        Markdown is supported in comment text.

        Args:
            issue_id: The issue identifier (e.g., "LIN-123" or UUID)
            comment: Comment text (markdown supported)
            config: Client configuration

        Returns:
            IssueResult with created comment data

        Example:
            >>> result = await client.create_comment(
            ...     issue_id="LIN-123",
            ...     comment="Fixed in v2.0.0. See commit abc123.",
            ...     config=config
            ... )
        """
        mutation = """
        mutation CreateComment($issueId: String!, $body: String!) {
            commentCreate(input: {
                issueId: $issueId,
                body: $body
            }) {
                success
                comment {
                    id
                    body
                    user {
                        id
                        name
                    }
                    createdAt
                    updatedAt
                }
            }
        }
        """

        variables = {
            "issueId": issue_id,
            "body": comment,
        }

        result = await self._execute_query(mutation, variables, config)

        if not result.success:
            return result

        # Extract comment data from response
        comment_data = result.data.get("data", {}).get("commentCreate", {})

        if not comment_data.get("success"):
            return IssueResult.from_error(
                "Failed to create comment",
                status_code=400,
            )

        return IssueResult.from_success(
            data={"comment": comment_data.get("comment")},
            status_code=result.status_code,
        )

    async def update_status(
        self,
        issue_id: str,
        status: IssueStatus,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Update the status of a Linear issue.

        Changes the issue's state by mapping IssueStatus to Linear's state types.
        Requires that the target state exists in the team's workflow.

        Args:
            issue_id: The issue identifier (e.g., "LIN-123" or UUID)
            status: New status from IssueStatus enum
            config: Client configuration

        Returns:
            IssueResult with updated issue data

        Example:
            >>> result = await client.update_status(
            ...     issue_id="LIN-123",
            ...     status=IssueStatus.IN_PROGRESS,
            ...     config=config
            ... )

        Note:
            Linear teams can have custom workflows. This method uses
            standard state types which may not match all team workflows.
        """
        # Map IssueStatus to Linear state type
        state_type = self.STATUS_TO_STATE_TYPE.get(status)

        if not state_type:
            return IssueResult.from_error(
                f"Unsupported status for Linear: {status}. "
                f"Valid statuses: {list(self.STATUS_TO_STATE_TYPE.keys())}",
                status_code=400,
            )

        # First, query the team to find the state ID for this state type
        # This is more complex than GitHub/GitLab as Linear uses state IDs
        query = """
        query IssueStates($issueId: String!) {
            issue(id: $issueId) {
                team {
                    states {
                        nodes {
                            id
                            type
                            name
                        }
                    }
                }
            }
        }
        """

        variables = {"issueId": issue_id}
        query_result = await self._execute_query(query, variables, config)

        if not query_result.success:
            return query_result

        # Find the state ID for the desired state type
        team_states = (
            query_result.data.get("data", {})
            .get("issue", {})
            .get("team", {})
            .get("states", {})
            .get("nodes", [])
        )

        state_id = None
        for state in team_states:
            if state.get("type") == state_type:
                state_id = state.get("id")
                break

        if not state_id:
            return IssueResult.from_error(
                f"State type '{state_type}' not found in team workflow. "
                f"Available states: {[s.get('type') for s in team_states]}",
                status_code=400,
            )

        # Now update the issue with the state ID
        mutation = """
        mutation UpdateIssue($issueId: String!, $stateId: String!) {
            issueUpdate(input: {
                id: $issueId,
                stateId: $stateId
            }) {
                success
                issue {
                    id
                    identifier
                    title
                    state {
                        id
                        name
                        type
                    }
                }
            }
        }
        """

        variables = {
            "issueId": issue_id,
            "stateId": state_id,
        }

        result = await self._execute_query(mutation, variables, config)

        if not result.success:
            return result

        # Extract updated issue data
        update_data = result.data.get("data", {}).get("issueUpdate", {})

        if not update_data.get("success"):
            return IssueResult.from_error(
                "Failed to update issue status",
                status_code=400,
            )

        return IssueResult.from_success(
            data={"issue": update_data.get("issue")},
            status_code=result.status_code,
        )

    async def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        config: IssueClientConfig,
    ) -> bool:
        """
        Verify a Linear webhook signature.

        Linear webhooks are signed using HMAC-SHA256 with the webhook secret.
        The signature is provided in the `Linear-Signature` header
        with format: `sha256=<hex_digest>`.

        Linear also provides a timestamp in `Linear-Request-Timestamp` header
        to prevent replay attacks.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from Linear-Signature header
            config: Client configuration with webhook_secret

        Returns:
            True if signature is valid, False otherwise

        Example:
            >>> is_valid = await client.verify_webhook(
            ...     payload=request.body,
            ...     signature=request.headers["Linear-Signature"],
            ...     config=config
            ... )

        Security:
            Always verify webhook signatures to ensure requests
            originated from Linear and not a malicious actor.
        """
        if not config.webhook_secret:
            # No secret configured, cannot verify
            return False

        if not signature:
            return False

        # Linear signature format: "sha256=<hex_signature>"
        if not signature.startswith("sha256="):
            return False

        # Extract the signature hash
        linear_signature = signature[7:]  # Remove "sha256=" prefix

        # Compute HMAC-SHA256 of payload
        expected_signature = hmac.new(
            config.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(linear_signature, expected_signature)

    async def get_rate_limit(
        self,
        config: IssueClientConfig,
    ) -> Optional[dict[str, Any]]:
        """
        Get current Linear API rate limit status.

        Linear GraphQL API has rate limits based on query complexity.
        This information is returned in response headers.

        Args:
            config: Client configuration

        Returns:
            Dict with rate limit info, or None if not available:
            - limit: Total complexity points allowed
            - remaining: Remaining complexity points
            - reset: Unix timestamp when limit resets
            - query_cost: Cost of last query

        Note:
            Linear's rate limiting is based on query complexity, not
            request count. The actual limits are returned in response
            headers which are not accessible through make_http_request.
        """
        # Linear rate limit info is in response headers
        # which we don't have access to in the current implementation
        # This is a placeholder for future enhancement
        return None

    async def fetch_issue_comments(
        self,
        issue_id: str,
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Fetch all comments for a Linear issue.

        Retrieves all comments associated with an issue in chronological order.

        Args:
            issue_id: The issue identifier (e.g., "LIN-123" or UUID)
            config: Client configuration

        Returns:
            IssueResult with list of comments in `data` field

        Example:
            >>> result = await client.fetch_issue_comments("LIN-123", config)
            >>> if result.success:
            ...     comments = result.data["comments"]
        """
        query = """
        query IssueComments($issueId: String!) {
            issue(id: $issueId) {
                comments {
                    nodes {
                        id
                        body
                        user {
                            id
                            name
                            email
                            avatarUrl
                        }
                        createdAt
                        updatedAt
                        parent {
                            id
                        }
                    }
                }
            }
        }
        """

        variables = {"issueId": issue_id}
        result = await self._execute_query(query, variables, config)

        if not result.success:
            return result

        # Extract comments from response
        comments = (
            result.data.get("data", {})
            .get("issue", {})
            .get("comments", {})
            .get("nodes", [])
        )

        return IssueResult.from_success(
            data={"comments": comments},
            status_code=result.status_code,
        )

    async def add_labels(
        self,
        issue_id: str,
        labels: list[str],
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Add labels to a Linear issue.

        Adds one or more labels to an issue by name.
        Labels that don't exist will be ignored.

        Args:
            issue_id: The issue identifier (e.g., "LIN-123" or UUID)
            labels: List of label names to add
            config: Client configuration

        Returns:
            IssueResult with updated issue data

        Example:
            >>> result = await client.add_labels(
            ...     issue_id="LIN-123",
            ...     labels=["bug", "critical", "triaged"],
            ...     config=config
            ... )
        """
        # First, fetch the issue to get team context
        fetch_result = await self.fetch_issue(issue_id, config)

        if not fetch_result.success:
            return fetch_result

        issue_data = fetch_result.data.get("issue", {})
        team_id = issue_data.get("team", {}).get("id")

        if not team_id:
            return IssueResult.from_error(
                "Could not determine team for issue",
                status_code=400,
            )

        # Query to find label IDs in the team
        query = """
        query TeamLabels($teamId: String!) {
            team(id: $teamId) {
                labels {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
        """

        variables = {"teamId": team_id}
        query_result = await self._execute_query(query, variables, config)

        if not query_result.success:
            return query_result

        # Build a map of label names to IDs
        team_labels = (
            query_result.data.get("data", {})
            .get("team", {})
            .get("labels", {})
            .get("nodes", [])
        )

        label_map = {label["name"]: label["id"] for label in team_labels}

        # Find IDs for requested labels
        label_ids_to_add = []
        for label_name in labels:
            if label_name in label_map:
                label_ids_to_add.append(label_map[label_name])

        if not label_ids_to_add:
            return IssueResult.from_error(
                f"None of the specified labels found in team: {labels}",
                status_code=400,
            )

        # Get existing labels
        existing_label_ids = [
            label["id"] for label in issue_data.get("labels", {}).get("nodes", [])
        ]

        # Combine existing and new labels
        all_label_ids = list(set(existing_label_ids + label_ids_to_add))

        # Update the issue with all labels
        mutation = """
        mutation UpdateIssueLabels($issueId: String!, $labelIds: [String!]!) {
            issueUpdate(input: {
                id: $issueId,
                labelIds: $labelIds
            }) {
                success
                issue {
                    id
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                }
            }
        }
        """

        variables = {
            "issueId": issue_id,
            "labelIds": all_label_ids,
        }

        result = await self._execute_query(mutation, variables, config)

        if not result.success:
            return result

        update_data = result.data.get("data", {}).get("issueUpdate", {})

        if not update_data.get("success"):
            return IssueResult.from_error(
                "Failed to add labels to issue",
                status_code=400,
            )

        return IssueResult.from_success(
            data={"issue": update_data.get("issue")},
            status_code=result.status_code,
        )

    async def set_labels(
        self,
        issue_id: str,
        labels: list[str],
        config: IssueClientConfig,
    ) -> IssueResult:
        """
        Replace all labels on a Linear issue.

        Replaces all existing labels with the provided list.
        Use this to completely reset an issue's labels.

        Args:
            issue_id: The issue identifier (e.g., "LIN-123" or UUID)
            labels: List of label names to set
            config: Client configuration

        Returns:
            IssueResult with updated issue data

        Example:
            >>> result = await client.set_labels(
            ...     issue_id="LIN-123",
            ...     labels=["bug", "high-priority"],
            ...     config=config
            ... )
        """
        # Fetch team and label IDs (same logic as add_labels)
        fetch_result = await self.fetch_issue(issue_id, config)

        if not fetch_result.success:
            return fetch_result

        issue_data = fetch_result.data.get("issue", {})
        team_id = issue_data.get("team", {}).get("id")

        if not team_id:
            return IssueResult.from_error(
                "Could not determine team for issue",
                status_code=400,
            )

        # Query to find label IDs
        query = """
        query TeamLabels($teamId: String!) {
            team(id: $teamId) {
                labels {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
        """

        variables = {"teamId": team_id}
        query_result = await self._execute_query(query, variables, config)

        if not query_result.success:
            return query_result

        team_labels = (
            query_result.data.get("data", {})
            .get("team", {})
            .get("labels", {})
            .get("nodes", [])
        )

        label_map = {label["name"]: label["id"] for label in team_labels}

        # Find IDs for all requested labels
        label_ids = []
        for label_name in labels:
            if label_name in label_map:
                label_ids.append(label_map[label_name])

        # Update the issue with only these labels
        mutation = """
        mutation UpdateIssueLabels($issueId: String!, $labelIds: [String!]!) {
            issueUpdate(input: {
                id: $issueId,
                labelIds: $labelIds
            }) {
                success
                issue {
                    id
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                }
            }
        }
        """

        variables = {
            "issueId": issue_id,
            "labelIds": label_ids,
        }

        result = await self._execute_query(mutation, variables, config)

        if not result.success:
            return result

        update_data = result.data.get("data", {}).get("issueUpdate", {})

        if not update_data.get("success"):
            return IssueResult.from_error(
                "Failed to set labels on issue",
                status_code=400,
            )

        return IssueResult.from_success(
            data={"issue": update_data.get("issue")},
            status_code=result.status_code,
        )
