"""
Autoflow Node Coordination Module

Provides data models for distributed agent coordination across multiple nodes.
Supports node registration, discovery, health monitoring, and work distribution.

Usage:
    from autoflow.coordination.node import Node, NodeStatus

    # Create a new node
    node = Node(
        id="node-001",
        address="localhost:8080",
        capabilities=["claude-code", "test-runner"],
        status=NodeStatus.ONLINE
    )

    # Update heartbeat
    node.update_heartbeat()
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    """Status of a node in the distributed cluster."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    DRAINING = "draining"
    UNHEALTHY = "unhealthy"


class Node(BaseModel):
    """
    Represents a node in the distributed cluster.

    A node is a participant in the distributed system that can execute
    agents and perform work. Each node has a unique ID, network address,
    set of capabilities, and current status.

    Attributes:
        id: Unique node identifier
        address: Network address (host:port format)
        capabilities: List of capabilities (e.g., agent types it can run)
        status: Current node status
        last_seen: Timestamp of last heartbeat/communication
        metadata: Additional node information

    Example:
        >>> node = Node(
        ...     id="node-001",
        ...     address="localhost:8080",
        ...     capabilities=["claude-code", "test-runner"]
        ... )
        >>> node.update_heartbeat()
        >>> print(node.is_online())
        True
    """

    id: str
    address: str = ""
    capabilities: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.OFFLINE
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_heartbeat(self) -> None:
        """
        Update the last_seen timestamp to current time.

        Should be called when receiving a heartbeat or communication
        from this node.

        Example:
            >>> node.update_heartbeat()
        """
        self.last_seen = datetime.utcnow()

    def is_online(self, timeout_seconds: int = 30) -> bool:
        """
        Check if the node is currently considered online.

        A node is online if its status is ONLINE and it has been
        seen recently (within the timeout period).

        Args:
            timeout_seconds: Seconds since last heartbeat before
                           considering node offline. Defaults to 30.

        Returns:
            True if node is online, False otherwise

        Example:
            >>> if node.is_online(timeout_seconds=60):
            ...     print("Node is available")
        """
        if self.status != NodeStatus.ONLINE:
            return False

        elapsed = (datetime.utcnow() - self.last_seen).total_seconds()
        return elapsed <= timeout_seconds

    def has_capability(self, capability: str) -> bool:
        """
        Check if this node has a specific capability.

        Args:
            capability: Capability name to check

        Returns:
            True if node has the capability, False otherwise

        Example:
            >>> if node.has_capability("claude-code"):
            ...     print("Can run Claude Code agent")
        """
        return capability in self.capabilities

    def add_capability(self, capability: str) -> None:
        """
        Add a capability to this node.

        Idempotent - if capability already exists, no change is made.

        Args:
            capability: Capability to add

        Example:
            >>> node.add_capability("test-runner")
        """
        if capability not in self.capabilities:
            self.capabilities.append(capability)

    def remove_capability(self, capability: str) -> bool:
        """
        Remove a capability from this node.

        Args:
            capability: Capability to remove

        Returns:
            True if capability was removed, False if it didn't exist

        Example:
            >>> node.remove_capability("deprecated-agent")
        """
        if capability in self.capabilities:
            self.capabilities.remove(capability)
            return True
        return False
