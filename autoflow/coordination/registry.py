"""
Autoflow Node Registry Module

Provides node registration, lookup, and discovery capabilities for distributed
agent coordination. Manages the registry of available nodes in the cluster with
support for filtering by status, capabilities, and health.

Usage:
    from autoflow.coordination.registry import NodeRegistry
    from autoflow.coordination.node import Node, NodeStatus

    # Create a registry
    registry = NodeRegistry()

    # Register nodes
    node1 = Node(id="node-001", address="localhost:8080", capabilities=["claude-code"])
    registry.register(node1)

    # Lookup nodes
    node = registry.lookup("node-001")
    online_nodes = registry.get_online_nodes()

    # List and filter
    all_nodes = registry.list_nodes()
    capable_nodes = registry.get_nodes_by_capability("claude-code")
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.coordination.node import Node, NodeStatus


class RegistryStats(BaseModel):
    """
    Statistics about the node registry.

    Attributes:
        total_nodes: Total number of registered nodes
        online_nodes: Number of online nodes
        offline_nodes: Number of offline nodes
        busy_nodes: Number of busy nodes
        unhealthy_nodes: Number of unhealthy nodes
        last_updated: Timestamp of last update

    Example:
        >>> stats = RegistryStats(total_nodes=10, online_nodes=8)
        >>> print(stats.online_percentage())
        80.0
    """

    total_nodes: int = 0
    online_nodes: int = 0
    offline_nodes: int = 0
    busy_nodes: int = 0
    unhealthy_nodes: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    def online_percentage(self) -> float:
        """
        Calculate the percentage of nodes that are online.

        Returns:
            Percentage of online nodes (0-100)

        Example:
            >>> stats = RegistryStats(total_nodes=10, online_nodes=8)
            >>> print(f"{stats.online_percentage():.1f}% online")
            80.0% online
        """
        if self.total_nodes == 0:
            return 0.0
        return (self.online_nodes / self.total_nodes) * 100

    def healthy_percentage(self) -> float:
        """
        Calculate the percentage of nodes that are healthy.

        Returns:
            Percentage of healthy nodes (0-100)

        Example:
            >>> stats = RegistryStats(total_nodes=10, unhealthy_nodes=1)
            >>> print(f"{stats.healthy_percentage():.1f}% healthy")
            90.0% healthy
        """
        if self.total_nodes == 0:
            return 0.0
        return ((self.total_nodes - self.unhealthy_nodes) / self.total_nodes) * 100


class NodeRegistry:
    """
    Registry for managing distributed nodes.

    Provides registration, lookup, and discovery capabilities for nodes
    in the distributed cluster. Supports filtering by status, capabilities,
    and health state.

    The registry maintains an in-memory collection of nodes for fast access
    and can optionally persist state to disk for recovery.

    Attributes:
        nodes: Dictionary mapping node IDs to Node objects

    Example:
        >>> registry = NodeRegistry()
        >>> node = Node(id="node-001", address="localhost:8080")
        >>> registry.register(node)
        >>> found = registry.lookup("node-001")
        >>> assert found.id == "node-001"
    """

    def __init__(self, persist_path: Optional[Path] = None):
        """
        Initialize the NodeRegistry.

        Args:
            persist_path: Optional path to persist registry state.
                         If provided, loads existing state on initialization.

        Example:
            >>> # In-memory registry
            >>> registry = NodeRegistry()
            >>>
            >>> # Persistent registry
            >>> registry = NodeRegistry(persist_path=Path(".autoflow/nodes"))
        """
        self._nodes: dict[str, Node] = {}
        self._persist_path = persist_path

        if persist_path:
            self._load_from_disk()

    def register(self, node: Node) -> None:
        """
        Register a node in the registry.

        If a node with the same ID already exists, it will be updated
        with the new node information.

        Args:
            node: Node to register

        Example:
            >>> node = Node(
            ...     id="node-001",
            ...     address="localhost:8080",
            ...     capabilities=["claude-code"]
            ... )
            >>> registry.register(node)
        """
        self._nodes[node.id] = node
        self._persist_to_disk()

    def unregister(self, node_id: str) -> bool:
        """
        Unregister a node from the registry.

        Args:
            node_id: ID of the node to unregister

        Returns:
            True if node was unregistered, False if not found

        Example:
            >>> if registry.unregister("node-001"):
            ...     print("Node removed")
        """
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._persist_to_disk()
            return True
        return False

    def lookup(self, node_id: str) -> Optional[Node]:
        """
        Look up a node by ID.

        Args:
            node_id: ID of the node to find

        Returns:
            Node if found, None otherwise

        Example:
            >>> node = registry.lookup("node-001")
            >>> if node:
            ...     print(f"Found node at {node.address}")
        """
        return self._nodes.get(node_id)

    def list_nodes(
        self,
        status: Optional[NodeStatus] = None,
        capability: Optional[str] = None,
    ) -> list[Node]:
        """
        List all registered nodes, optionally filtered.

        Args:
            status: Optional filter by node status
            capability: Optional filter by capability (nodes must have this capability)

        Returns:
            List of nodes matching the criteria

        Example:
            >>> # Get all nodes
            >>> all_nodes = registry.list_nodes()
            >>>
            >>> # Get only online nodes
            >>> online_nodes = registry.list_nodes(status=NodeStatus.ONLINE)
            >>>
            >>> # Get nodes with specific capability
            >>> capable_nodes = registry.list_nodes(capability="claude-code")
        """
        nodes = list(self._nodes.values())

        if status:
            nodes = [n for n in nodes if n.status == status]

        if capability:
            nodes = [n for n in nodes if n.has_capability(capability)]

        return nodes

    def get_online_nodes(
        self, timeout_seconds: int = 30
    ) -> list[Node]:
        """
        Get all nodes that are currently online.

        A node is considered online if its status is ONLINE and it has
        been seen recently (within the timeout period).

        Args:
            timeout_seconds: Seconds since last heartbeat before
                           considering node offline. Defaults to 30.

        Returns:
            List of online nodes

        Example:
            >>> online = registry.get_online_nodes(timeout_seconds=60)
            >>> print(f"Found {len(online)} online nodes")
        """
        return [
            node
            for node in self._nodes.values()
            if node.is_online(timeout_seconds=timeout_seconds)
        ]

    def get_nodes_by_capability(self, capability: str) -> list[Node]:
        """
        Get all nodes that have a specific capability.

        Args:
            capability: Capability name to filter by

        Returns:
            List of nodes with the capability

        Example:
            >>> nodes = registry.get_nodes_by_capability("test-runner")
            >>> for node in nodes:
            ...     print(f"{node.id} can run tests")
        """
        return [
            node
            for node in self._nodes.values()
            if node.has_capability(capability)
        ]

    def get_available_nodes(
        self, capability: Optional[str] = None
    ) -> list[Node]:
        """
        Get nodes that are available for work assignment.

        A node is available if it is online and not currently busy.

        Args:
            capability: Optional capability filter

        Returns:
            List of available nodes

        Example:
            >>> nodes = registry.get_available_nodes(capability="claude-code")
            >>> if nodes:
            ...     print(f"Found {len(nodes)} nodes ready for work")
        """
        nodes = self.get_online_nodes()

        # Filter out busy nodes
        nodes = [n for n in nodes if n.status != NodeStatus.BUSY]

        # Filter by capability if specified
        if capability:
            nodes = [n for n in nodes if n.has_capability(capability)]

        return nodes

    def update_node_status(
        self, node_id: str, status: NodeStatus
    ) -> bool:
        """
        Update the status of a node.

        Args:
            node_id: ID of the node to update
            status: New status

        Returns:
            True if updated, False if node not found

        Example:
            >>> registry.update_node_status("node-001", NodeStatus.BUSY)
        """
        node = self.lookup(node_id)
        if node:
            node.status = status
            node.update_heartbeat()
            self._persist_to_disk()
            return True
        return False

    def update_heartbeat(self, node_id: str) -> bool:
        """
        Update the heartbeat timestamp for a node.

        Called when receiving communication from a node to confirm
        it is still alive.

        Args:
            node_id: ID of the node

        Returns:
            True if updated, False if node not found

        Example:
            >>> registry.update_heartbeat("node-001")
        """
        node = self.lookup(node_id)
        if node:
            node.update_heartbeat()
            self._persist_to_disk()
            return True
        return False

    def get_node_count(self) -> int:
        """
        Get the total number of registered nodes.

        Returns:
            Total node count

        Example:
            >>> count = registry.get_node_count()
            >>> print(f"Registry has {count} nodes")
        """
        return len(self._nodes)

    def get_stats(self) -> RegistryStats:
        """
        Get statistics about the registry.

        Returns:
            RegistryStats object with current statistics

        Example:
            >>> stats = registry.get_stats()
            >>> print(f"{stats.online_nodes}/{stats.total_nodes} online")
        """
        nodes = list(self._nodes.values())

        return RegistryStats(
            total_nodes=len(nodes),
            online_nodes=len([n for n in nodes if n.status == NodeStatus.ONLINE]),
            offline_nodes=len([n for n in nodes if n.status == NodeStatus.OFFLINE]),
            busy_nodes=len([n for n in nodes if n.status == NodeStatus.BUSY]),
            unhealthy_nodes=len(
                [n for n in nodes if n.status == NodeStatus.UNHEALTHY]
            ),
        )

    def clear(self) -> None:
        """
        Clear all nodes from the registry.

        Example:
            >>> registry.clear()
            >>> assert registry.get_node_count() == 0
        """
        self._nodes.clear()
        self._persist_to_disk()

    # === Persistence Methods ===

    def _load_from_disk(self) -> None:
        """
        Load registry state from disk.

        Loads previously persisted node data from the persist path.
        Silently fails if file doesn't exist or is invalid.
        """
        if not self._persist_path:
            return

        import json

        try:
            if self._persist_path.exists():
                with open(self._persist_path, encoding="utf-8") as f:
                    data = json.load(f)

                for node_data in data.get("nodes", []):
                    node = Node(**node_data)
                    self._nodes[node.id] = node
        except (json.JSONDecodeError, TypeError, ValueError):
            # If file is corrupted, start fresh
            self._nodes.clear()

    def _persist_to_disk(self) -> None:
        """
        Persist registry state to disk.

        Writes current node data to the persist path.
        Silently fails if persist path is not set or write fails.
        """
        if not self._persist_path:
            return

        import json

        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "nodes": [node.model_dump() for node in self._nodes.values()],
                "updated_at": datetime.utcnow().isoformat(),
            }

            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except (OSError, ValueError):
            # Fail silently if we can't persist
            pass
