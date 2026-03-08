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

from typing import Optional

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
