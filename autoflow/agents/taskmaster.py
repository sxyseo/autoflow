"""
Autoflow Taskmaster AI Integration Module

Provides direct API integration with Taskmaster AI for enhanced task
graph management. Enables bidirectional sync of tasks, priorities, and
execution state between Autoflow and Taskmaster.

Usage:
    from autoflow.agents.taskmaster import TaskmasterConfig, TaskmasterAPIClient

    config = TaskmasterConfig(
        api_base_url="https://api.taskmaster.ai",
        api_key="your-api-key"
    )
    client = TaskmasterAPIClient(config)
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, field_validator


class TaskmasterConfig(BaseModel):
    """
    Configuration for Taskmaster AI API integration.

    Contains all settings needed to connect to and interact with the
    Taskmaster AI API, including authentication credentials, endpoints,
    and behavior options.

    Attributes:
        api_base_url: Base URL for the Taskmaster API
        api_key: API key for authentication
        workspace_id: Optional workspace ID (if using multi-tenant workspace)
        timeout_seconds: Request timeout in seconds
        retry_attempts: Number of retry attempts for failed requests
        retry_delay_seconds: Delay between retry attempts
        verify_ssl: Whether to verify SSL certificates
        enabled: Whether Taskmaster integration is enabled
    """

    api_base_url: str = "https://api.taskmaster.ai"
    api_key: Optional[str] = None
    workspace_id: Optional[str] = None
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: int = 1
    verify_ssl: bool = True
    enabled: bool = True

    @field_validator("api_base_url", mode="before")
    @classmethod
    def normalize_api_base_url(cls, v: str) -> str:
        """
        Normalize the API base URL by removing trailing slashes.

        Args:
            v: The API base URL to normalize

        Returns:
            Normalized URL without trailing slash
        """
        if isinstance(v, str):
            return v.rstrip("/")
        return v

    @field_validator("timeout_seconds", "retry_attempts", "retry_delay_seconds", mode="before")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """
        Validate that timeout and retry values are positive integers.

        Args:
            v: The value to validate

        Returns:
            The validated value

        Raises:
            ValueError: If the value is not positive
        """
        if isinstance(v, int) and v < 0:
            raise ValueError("Value must be a positive integer")
        return v

    @property
    def is_configured(self) -> bool:
        """
        Check if the configuration is complete and ready to use.

        Returns:
            True if an API key is configured, False otherwise
        """
        return self.api_key is not None and self.api_key != ""

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get authentication headers for API requests.

        Returns:
            Dictionary of headers including Authorization
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


class TaskmasterAPIClient:
    """
    API client for Taskmaster AI integration.

    Provides a Python interface to the Taskmaster AI API with support for:
    - Bearer token authentication
    - Async HTTP requests with timeout handling
    - Automatic retry logic for failed requests
    - SSL verification control
    - Workspace-scoped requests

    The client uses httpx for async HTTP operations and supports
    both individual requests and session-based connections.

    Attributes:
        config: TaskmasterConfig instance with connection settings
        _client: Optional httpx.AsyncClient for connection pooling

    Example:
        >>> config = TaskmasterConfig(
        ...     api_base_url="https://api.taskmaster.ai",
        ...     api_key="your-api-key"
        ... )
        >>> client = TaskmasterAPIClient(config)
        >>> response = await client.get("/tasks")
    """

    def __init__(
        self,
        config: TaskmasterConfig,
    ) -> None:
        """
        Initialize the Taskmaster API client.

        Args:
            config: TaskmasterConfig with API credentials and settings

        Raises:
            ValueError: If config is not properly configured
        """
        if not config.is_configured:
            raise ValueError(
                "TaskmasterConfig must have an api_key to use the API client"
            )
        if not config.enabled:
            raise ValueError(
                "TaskmasterConfig must have enabled=True to use the API client"
            )

        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create the HTTP client.

        Creates an httpx.AsyncClient with appropriate settings if one
        doesn't already exist. The client is cached for connection reuse.

        Returns:
            Configured httpx.AsyncClient instance
        """
        if self._client is None:
            timeout = httpx.Timeout(self.config.timeout_seconds)
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

            self._client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                timeout=timeout,
                limits=limits,
                verify=self.config.verify_ssl,
                headers=self.config.get_auth_headers(),
            )
        return self._client

    async def close(self) -> None:
        """
        Close the HTTP client and release resources.

        Should be called when done using the client to properly
        close network connections.
        """
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with retry logic.

        Handles HTTP requests to the Taskmaster API with automatic
        retry on transient failures. Includes timeout handling and
        error parsing.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path (will be appended to base URL)
            **kwargs: Additional arguments passed to httpx request

        Returns:
            Parsed JSON response as a dictionary

        Raises:
            httpx.HTTPStatusError: If request fails after all retries
            httpx.TimeoutException: If request times out
            httpx.HTTPError: For other HTTP-related errors

        Example:
            >>> data = await client._make_request("GET", "/tasks")
            >>> print(data["tasks"])
        """
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.config.retry_attempts):
            try:
                response = await client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise
                # Retry server errors (5xx) with delay
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds)

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                # Retry network errors with delay
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds)

        # All retries exhausted
        raise last_error if last_error else httpx.HTTPError("Request failed")

    async def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Make a GET request to the API.

        Args:
            endpoint: API endpoint path
            params: Query parameters to include in the request

        Returns:
            Parsed JSON response

        Example:
            >>> tasks = await client.get("/tasks", params={"status": "pending"})
        """
        return await self._make_request("GET", endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Make a POST request to the API.

        Args:
            endpoint: API endpoint path
            data: Form data to send in the request body
            json: JSON data to send in the request body

        Returns:
            Parsed JSON response

        Example:
            >>> result = await client.post("/tasks", json={"title": "New task"})
        """
        return await self._make_request("POST", endpoint, data=data, json=json)

    async def put(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Make a PUT request to the API.

        Args:
            endpoint: API endpoint path
            data: Form data to send in the request body
            json: JSON data to send in the request body

        Returns:
            Parsed JSON response

        Example:
            >>> result = await client.put("/tasks/123", json={"status": "done"})
        """
        return await self._make_request("PUT", endpoint, data=data, json=json)

    async def delete(
        self,
        endpoint: str,
    ) -> dict[str, Any]:
        """
        Make a DELETE request to the API.

        Args:
            endpoint: API endpoint path

        Returns:
            Parsed JSON response

        Example:
            >>> result = await client.delete("/tasks/123")
        """
        return await self._make_request("DELETE", endpoint)

    async def check_health(self) -> bool:
        """
        Check if the Taskmaster API is accessible.

        Makes a simple request to verify connectivity and authentication.

        Returns:
            True if API is accessible and authentication is valid

        Example:
            >>> if await client.check_health():
            ...     print("API is healthy")
        """
        try:
            # Try to get workspace info or a simple endpoint
            if self.config.workspace_id:
                endpoint = f"/workspaces/{self.config.workspace_id}"
            else:
                endpoint = "/health" or "/"

            await self._make_request("GET", endpoint)
            return True
        except Exception:
            return False

    def __repr__(self) -> str:
        """Return string representation of the client."""
        return (
            f"TaskmasterAPIClient("
            f"api_base_url={self.config.api_base_url!r}, "
            f"workspace_id={self.config.workspace_id!r})"
        )

    async def __aenter__(self) -> "TaskmasterAPIClient":
        """
        Enter async context manager.

        Returns:
            The client instance
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[Any],
    ) -> None:
        """
        Exit async context manager.

        Ensures the HTTP client is properly closed.
        """
        await self.close()
