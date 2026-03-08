"""
Autoflow Node Communication Client

Provides async HTTP client for node-to-node communication in distributed
agent coordination. Supports node registration, heartbeat, work assignment,
and status queries across the cluster.

Usage:
    from autoflow.coordination.client import NodeClient

    # Create a client
    client = NodeClient()

    # Register with a remote node
    await client.register_node(
        node_id="node-001",
        address="http://node-001:8080",
        capabilities=["claude-code"]
    )

    # Send heartbeat
    await client.send_heartbeat("node-001", "http://node-001:8080")

    # Assign work to a node
    await client.assign_work(
        work_id="work-001",
        task="Implement feature X",
        node_address="http://node-001:8080"
    )
"""

from __future__ import annotations

import json
from typing import Any, Optional

from aiohttp import ClientError, ClientSession, ClientTimeout
from pydantic import BaseModel

from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.work_queue import WorkItem, WorkItemStatus


class NodeClientError(Exception):
    """Exception raised when node communication fails."""

    def __init__(
        self,
        message: str,
        node_address: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        """
        Initialize the error.

        Args:
            message: Error message
            node_address: Address of the node that failed
            status_code: HTTP status code if applicable
        """
        self.node_address = node_address
        self.status_code = status_code
        super().__init__(message)


class NodeClient:
    """
    Async HTTP client for node-to-node communication.

    Provides methods for communicating with other nodes in the cluster,
    including registration, heartbeat, work assignment, and status queries.

    The client uses connection pooling and configurable timeouts for
    efficient communication across potentially unreliable networks.

    Attributes:
        DEFAULT_TIMEOUT: Default request timeout in seconds
        DEFAULT_RETRY_COUNT: Default number of retries for failed requests

    Example:
        >>> client = NodeClient(timeout_seconds=30)
        >>> # Register with another node
        >>> await client.register_node(
        ...     node_id="node-001",
        ...     address="http://node-001:8080",
        ...     capabilities=["claude-code"]
        ... )
        >>> # Send heartbeat
        >>> await client.send_heartbeat("node-001", "http://node-001:8080")
    """

    DEFAULT_TIMEOUT: int = 30
    DEFAULT_RETRY_COUNT: int = 3

    def __init__(
        self,
        timeout_seconds: Optional[int] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        """
        Initialize the NodeClient.

        Args:
            timeout_seconds: Request timeout in seconds (defaults to DEFAULT_TIMEOUT)
            retry_count: Number of retries for failed requests (defaults to DEFAULT_RETRY_COUNT)

        Example:
            >>> # Use defaults
            >>> client = NodeClient()
            >>>
            >>> # Custom timeout
            >>> client = NodeClient(timeout_seconds=60)
        """
        self._timeout = timeout_seconds or self.DEFAULT_TIMEOUT
        self._retry_count = retry_count or self.DEFAULT_RETRY_COUNT
        self._session: Optional[ClientSession] = None

    async def _get_session(self) -> ClientSession:
        """
        Get or create the aiohttp session.

        Uses a single session with connection pooling for efficient
        repeated requests.

        Returns:
            ClientSession for making HTTP requests
        """
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self._timeout)
            self._session = ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """
        Close the HTTP session and release resources.

        Should be called when done using the client.

        Example:
            >>> client = NodeClient()
            >>> await client.register_node(...)
            >>> await client.close()
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> NodeClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager and close resources."""
        await self.close()

    async def _post(
        self,
        url: str,
        data: dict[str, Any],
        node_address: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a POST request to a node.

        Args:
            url: Full URL to send request to
            data: Request body data (will be JSON-encoded)
            node_address: Optional node address for error reporting

        Returns:
            Parsed JSON response

        Raises:
            NodeClientError: If the request fails
        """
        session = await self._get_session()

        try:
            async with session.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise NodeClientError(
                        f"Request failed with status {response.status}: {error_text}",
                        node_address=node_address,
                        status_code=response.status,
                    )

                return await response.json()

        except ClientError as e:
            raise NodeClientError(
                f"Network error: {str(e)}",
                node_address=node_address,
            ) from e

    async def _get(
        self,
        url: str,
        node_address: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a GET request to a node.

        Args:
            url: Full URL to send request to
            node_address: Optional node address for error reporting

        Returns:
            Parsed JSON response

        Raises:
            NodeClientError: If the request fails
        """
        session = await self._get_session()

        try:
            async with session.get(url) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise NodeClientError(
                        f"Request failed with status {response.status}: {error_text}",
                        node_address=node_address,
                        status_code=response.status,
                    )

                return await response.json()

        except ClientError as e:
            raise NodeClientError(
                f"Network error: {str(e)}",
                node_address=node_address,
            ) from e

    async def register_node(
        self,
        node_id: str,
        address: str,
        capabilities: list[str],
        target_address: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Node:
        """
        Register this node with a remote node in the cluster.

        Args:
            node_id: This node's ID
            address: This node's address
            capabilities: This node's capabilities
            target_address: Address of the node to register with
            metadata: Optional additional metadata

        Returns:
            Node registration response

        Raises:
            NodeClientError: If registration fails

        Example:
            >>> node = await client.register_node(
            ...     node_id="node-002",
            ...     address="http://node-002:8080",
            ...     capabilities=["claude-code", "test-runner"],
            ...     target_address="http://node-001:8080"
            ... )
        """
        url = f"{target_address}/api/v1/nodes/register"

        payload = {
            "node_id": node_id,
            "address": address,
            "capabilities": capabilities,
            "metadata": metadata or {},
        }

        response = await self._post(url, payload, target_address)

        return Node(
            id=response["node"]["id"],
            address=response["node"]["address"],
            capabilities=response["node"]["capabilities"],
            status=NodeStatus(response["node"]["status"]),
            metadata=response["node"].get("metadata", {}),
        )

    async def send_heartbeat(
        self,
        node_id: str,
        target_address: str,
    ) -> bool:
        """
        Send a heartbeat to a remote node.

        Args:
            node_id: This node's ID
            target_address: Address of the node to send heartbeat to

        Returns:
            True if heartbeat was acknowledged

        Raises:
            NodeClientError: If heartbeat fails

        Example:
            >>> await client.send_heartbeat(
            ...     node_id="node-002",
            ...     target_address="http://node-001:8080"
            ... )
        """
        url = f"{target_address}/api/v1/nodes/{node_id}/heartbeat"

        payload = {"node_id": node_id}
        await self._post(url, payload, target_address)

        return True

    async def get_node_status(
        self,
        target_address: str,
    ) -> dict[str, Any]:
        """
        Get the status of a remote node.

        Args:
            target_address: Address of the node to query

        Returns:
            Dictionary with node status information

        Raises:
            NodeClientError: If request fails

        Example:
            >>> status = await client.get_node_status("http://node-001:8080")
            >>> print(f"Node {status['node_id']} is {status['status']}")
        """
        url = f"{target_address}/api/v1/status"

        response = await self._get(url, target_address)

        return {
            "node_id": response["node_id"],
            "status": response["status"],
            "capabilities": response.get("capabilities", []),
            "last_seen": response.get("last_seen"),
        }

    async def assign_work(
        self,
        work_id: str,
        task: str,
        node_address: str,
        priority: int = 5,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkItem:
        """
        Assign a work item to a remote node.

        Args:
            work_id: Unique work item ID
            task: Task description
            node_address: Address of the node to assign work to
            priority: Work priority (1-10, higher is more urgent)
            metadata: Optional additional metadata

        Returns:
            WorkItem representing the assigned work

        Raises:
            NodeClientError: If assignment fails

        Example:
            >>> work = await client.assign_work(
            ...     work_id="work-001",
            ...     task="Implement feature X",
            ...     node_address="http://node-001:8080",
            ...     priority=8
            ... )
        """
        url = f"{node_address}/api/v1/work/assign"

        payload = {
            "work_id": work_id,
            "task": task,
            "priority": priority,
            "metadata": metadata or {},
        }

        response = await self._post(url, payload, node_address)

        return WorkItem(
            id=response["work"]["id"],
            task=response["work"]["task"],
            status=WorkItemStatus(response["work"]["status"]),
            assigned_node=response["work"]["assigned_node"],
            priority=response["work"]["priority"],
            metadata=response["work"].get("metadata", {}),
        )

    async def get_work_status(
        self,
        work_id: str,
        node_address: str,
    ) -> dict[str, Any]:
        """
        Get the status of a work item from a remote node.

        Args:
            work_id: Work item ID to query
            node_address: Address of the node holding the work

        Returns:
            Dictionary with work status information

        Raises:
            NodeClientError: If request fails

        Example:
            >>> status = await client.get_work_status(
            ...     work_id="work-001",
            ...     node_address="http://node-001:8080"
            ... )
            >>> print(f"Work is {status['status']}")
        """
        url = f"{node_address}/api/v1/work/{work_id}/status"

        response = await self._get(url, node_address)

        return {
            "work_id": response["work_id"],
            "status": response["status"],
            "task": response.get("task"),
            "assigned_node": response.get("assigned_node"),
            "started_at": response.get("started_at"),
            "completed_at": response.get("completed_at"),
            "error": response.get("error"),
        }

    async def update_work_status(
        self,
        work_id: str,
        status: WorkItemStatus,
        node_address: str,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a work item on a remote node.

        Args:
            work_id: Work item ID to update
            status: New status
            node_address: Address of the node holding the work
            error: Optional error message if status is FAILED

        Returns:
            True if update was acknowledged

        Raises:
            NodeClientError: If update fails

        Example:
            >>> await client.update_work_status(
            ...     work_id="work-001",
            ...     status=WorkItemStatus.COMPLETED,
            ...     node_address="http://node-001:8080"
            ... )
        """
        url = f"{node_address}/api/v1/work/{work_id}/status"

        payload = {
            "status": status.value,
        }

        if error:
            payload["error"] = error

        await self._post(url, payload, node_address)

        return True

    async def discover_nodes(
        self,
        target_address: str,
    ) -> list[Node]:
        """
        Request node discovery information from a remote node.

        Args:
            target_address: Address of the node to query

        Returns:
            List of known nodes

        Raises:
            NodeClientError: If request fails

        Example:
            >>> nodes = await client.discover_nodes("http://node-001:8080")
            >>> for node in nodes:
            ...     print(f"Found {node.id} at {node.address}")
        """
        url = f"{target_address}/api/v1/nodes"

        response = await self._get(url, target_address)

        nodes = []
        for node_data in response.get("nodes", []):
            nodes.append(
                Node(
                    id=node_data["id"],
                    address=node_data["address"],
                    capabilities=node_data.get("capabilities", []),
                    status=NodeStatus(node_data["status"]),
                    metadata=node_data.get("metadata", {}),
                )
            )

        return nodes

    async def ping_node(
        self,
        target_address: str,
    ) -> bool:
        """
        Ping a node to check if it's responsive.

        Args:
            target_address: Address of the node to ping

        Returns:
            True if node responded successfully

        Raises:
            NodeClientError: If ping fails

        Example:
            >>> if await client.ping_node("http://node-001:8080"):
            ...     print("Node is up")
        """
        url = f"{target_address}/api/v1/ping"

        await self._get(url, target_address)

        return True

    def __repr__(self) -> str:
        """Return string representation of the client."""
        return (
            f"NodeClient("
            f"timeout={self._timeout}s, "
            f"retry_count={self._retry_count})"
        )
