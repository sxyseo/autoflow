"""
Autoflow Cluster State Module

Provides cluster-level state management for distributed agent coordination.
Tracks nodes, work distribution, and health status across the cluster.

Usage:
    from autoflow.coordination.cluster import ClusterState, ClusterStatus, WorkItem

    # Create a new cluster state
    cluster = ClusterState(cluster_id="prod-cluster")

    # Add a node
    from autoflow.coordination.node import Node
    node = Node(id="node-001", address="localhost:8080")
    cluster.add_node(node)

    # Assign work to a node
    work = WorkItem(id="work-001", task_id="task-001", assigned_node="node-001")
    cluster.add_work_item(work)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.coordination.node import Node, NodeStatus


class ClusterStatus(str, Enum):
    """Overall health status of the cluster."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    REBALANCING = "rebalancing"


class WorkItemStatus(str, Enum):
    """Status of a work item in the cluster."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItem(BaseModel):
    """
    Represents a unit of work assigned to a node.

    A work item represents a task or job that has been assigned to
    a specific node in the cluster for execution.

    Attributes:
        id: Unique work item identifier
        task_id: Associated task identifier
        assigned_node: ID of the node this work is assigned to
        status: Current work status
        created_at: When the work item was created
        started_at: When work started (None if not started)
        completed_at: When work completed (None if not completed)
        priority: Work priority (1-10, higher is more urgent)
        metadata: Additional work information

    Example:
        >>> work = WorkItem(
        ...     id="work-001",
        ...     task_id="task-001",
        ...     assigned_node="node-001",
        ...     priority=8
        ... )
        >>> work.start()
        >>> work.complete()
    """

    id: str
    task_id: str
    assigned_node: str
    status: WorkItemStatus = WorkItemStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    priority: int = 5
    metadata: dict[str, Any] = Field(default_factory=dict)

    def start(self) -> None:
        """
        Mark the work item as started.

        Sets the status to RUNNING and records the start time.

        Example:
            >>> work.start()
        """
        self.status = WorkItemStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(
        self,
        status: WorkItemStatus = WorkItemStatus.COMPLETED,
    ) -> None:
        """
        Mark the work item as completed.

        Args:
            status: Final status (defaults to COMPLETED)

        Example:
            >>> work.complete()
            >>> # or if it failed
            >>> work.complete(status=WorkItemStatus.FAILED)
        """
        self.status = status
        self.completed_at = datetime.utcnow()

    def duration_seconds(self) -> Optional[float]:
        """
        Calculate the duration of the work item.

        Returns:
            Duration in seconds, or None if not completed

        Example:
            >>> if work.completed_at:
            ...     print(f"Duration: {work.duration_seconds()}s")
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class ClusterState(BaseModel):
    """
    Represents the state of a distributed cluster.

    The ClusterState tracks all nodes in the cluster, work distribution
    across nodes, and overall cluster health. It provides methods for
    managing nodes, assigning work, and monitoring cluster status.

    Attributes:
        cluster_id: Unique cluster identifier
        nodes: Dictionary of nodes keyed by node ID
        work_items: Dictionary of work items keyed by work ID
        status: Overall cluster status
        created_at: When the cluster was created
        updated_at: When the cluster was last updated
        metadata: Additional cluster information

    Example:
        >>> from autoflow.coordination.node import Node
        >>> cluster = ClusterState(cluster_id="prod-cluster")
        >>> node = Node(id="node-001", address="localhost:8080")
        >>> cluster.add_node(node)
        >>> work = WorkItem(id="work-001", task_id="task-001", assigned_node="node-001")
        >>> cluster.add_work_item(work)
        >>> cluster.update_health_status()
        >>> print(cluster.status)
    """

    cluster_id: str
    nodes: dict[str, Node] = Field(default_factory=dict)
    work_items: dict[str, WorkItem] = Field(default_factory=dict)
    status: ClusterStatus = ClusterStatus.HEALTHY
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()

    def add_node(self, node: Node) -> None:
        """
        Add a node to the cluster.

        If a node with the same ID already exists, it will be replaced.

        Args:
            node: Node to add to the cluster

        Example:
            >>> node = Node(id="node-001", address="localhost:8080")
            >>> cluster.add_node(node)
        """
        self.nodes[node.id] = node
        self.touch()

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node from the cluster.

        Args:
            node_id: ID of the node to remove

        Returns:
            True if node was removed, False if not found

        Example:
            >>> if cluster.remove_node("node-001"):
            ...     print("Node removed")
        """
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.touch()
            return True
        return False

    def get_node(self, node_id: str) -> Optional[Node]:
        """
        Get a node by ID.

        Args:
            node_id: Node identifier

        Returns:
            Node if found, None otherwise

        Example:
            >>> node = cluster.get_node("node-001")
            >>> if node:
            ...     print(node.address)
        """
        return self.nodes.get(node_id)

    def get_online_nodes(self, timeout_seconds: int = 30) -> list[Node]:
        """
        Get all nodes that are currently online.

        Args:
            timeout_seconds: Seconds since last heartbeat before
                           considering node offline. Defaults to 30.

        Returns:
            List of online nodes

        Example:
            >>> online = cluster.get_online_nodes()
            >>> print(f"Online nodes: {len(online)}")
        """
        return [
            node
            for node in self.nodes.values()
            if node.is_online(timeout_seconds=timeout_seconds)
        ]

    def add_work_item(self, work: WorkItem) -> None:
        """
        Add a work item to the cluster.

        Args:
            work: Work item to add

        Example:
            >>> work = WorkItem(
            ...     id="work-001",
            ...     task_id="task-001",
            ...     assigned_node="node-001"
            ... )
            >>> cluster.add_work_item(work)
        """
        self.work_items[work.id] = work
        self.touch()

    def remove_work_item(self, work_id: str) -> bool:
        """
        Remove a work item from the cluster.

        Args:
            work_id: ID of the work item to remove

        Returns:
            True if work item was removed, False if not found

        Example:
            >>> if cluster.remove_work_item("work-001"):
            ...     print("Work item removed")
        """
        if work_id in self.work_items:
            del self.work_items[work_id]
            self.touch()
            return True
        return False

    def get_work_item(self, work_id: str) -> Optional[WorkItem]:
        """
        Get a work item by ID.

        Args:
            work_id: Work item identifier

        Returns:
            Work item if found, None otherwise

        Example:
            >>> work = cluster.get_work_item("work-001")
            >>> if work:
            ...     print(work.status)
        """
        return self.work_items.get(work_id)

    def get_work_for_node(self, node_id: str) -> list[WorkItem]:
        """
        Get all work items assigned to a specific node.

        Args:
            node_id: Node identifier

        Returns:
            List of work items assigned to the node

        Example:
            >>> work = cluster.get_work_for_node("node-001")
            >>> print(f"Node has {len(work)} work items")
        """
        return [
            work
            for work in self.work_items.values()
            if work.assigned_node == node_id
        ]

    def get_pending_work(self) -> list[WorkItem]:
        """
        Get all pending or assigned work items.

        Returns:
            List of work items that are pending or assigned

        Example:
            >>> pending = cluster.get_pending_work()
            >>> print(f"Pending work: {len(pending)}")
        """
        return [
            work
            for work in self.work_items.values()
            if work.status in (WorkItemStatus.PENDING, WorkItemStatus.ASSIGNED)
        ]

    def get_running_work(self) -> list[WorkItem]:
        """
        Get all currently running work items.

        Returns:
            List of work items that are currently running

        Example:
            >>> running = cluster.get_running_work()
            >>> print(f"Running work: {len(running)}")
        """
        return [
            work
            for work in self.work_items.values()
            if work.status == WorkItemStatus.RUNNING
        ]

    def update_health_status(self, timeout_seconds: int = 30) -> ClusterStatus:
        """
        Update the cluster health status based on node health.

        The cluster status is determined as follows:
        - HEALTHY: At least one online node and no offline nodes
        - DEGRADED: At least one online node but some offline nodes
        - UNHEALTHY: No online nodes

        Args:
            timeout_seconds: Seconds since last heartbeat before
                           considering node offline. Defaults to 30.

        Returns:
            The updated cluster status

        Example:
            >>> status = cluster.update_health_status()
            >>> print(f"Cluster status: {status}")
        """
        online_nodes = self.get_online_nodes(timeout_seconds=timeout_seconds)
        total_nodes = len(self.nodes)

        if total_nodes == 0:
            self.status = ClusterStatus.UNHEALTHY
        elif len(online_nodes) == total_nodes:
            self.status = ClusterStatus.HEALTHY
        elif len(online_nodes) > 0:
            self.status = ClusterStatus.DEGRADED
        else:
            self.status = ClusterStatus.UNHEALTHY

        self.touch()
        return self.status

    def get_node_count(self) -> dict[str, int]:
        """
        Get count of nodes by status.

        Returns:
            Dictionary with counts for each node status

        Example:
            >>> counts = cluster.get_node_count()
            >>> print(f"Online: {counts['online']}")
        """
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            status = node.status.value
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_work_count(self) -> dict[str, int]:
        """
        Get count of work items by status.

        Returns:
            Dictionary with counts for each work status

        Example:
            >>> counts = cluster.get_work_count()
            >>> print(f"Running: {counts['running']}")
        """
        counts: dict[str, int] = {}
        for work in self.work_items.values():
            status = work.status.value
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_available_capacity(self) -> dict[str, int]:
        """
        Get available capacity across all online nodes.

        Returns a dictionary mapping node IDs to their available capacity.
        This is a simple count-based metric - each node can handle unlimited
        work by default. Override this method to implement custom capacity logic.

        Returns:
            Dictionary with node IDs and available capacity

        Example:
            >>> capacity = cluster.get_available_capacity()
            >>> for node_id, cap in capacity.items():
            ...     print(f"{node_id}: {cap} slots available")
        """
        online_nodes = self.get_online_nodes()
        return {node.id: 999 for node in online_nodes}

    def find_least_loaded_node(
        self,
        capability: Optional[str] = None,
    ) -> Optional[Node]:
        """
        Find the online node with the least current work load.

        Args:
            capability: Optional capability filter - only consider nodes
                       with this capability

        Returns:
            Node with least work load, or None if no suitable node found

        Example:
            >>> node = cluster.find_least_loaded_node(capability="claude-code")
            >>> if node:
            ...     print(f"Assigning work to {node.id}")
        """
        online_nodes = self.get_online_nodes()

        # Filter by capability if specified
        if capability:
            online_nodes = [n for n in online_nodes if n.has_capability(capability)]

        if not online_nodes:
            return None

        # Find node with least running work
        least_loaded = None
        min_work = float("inf")

        for node in online_nodes:
            running_work = len(self.get_work_for_node(node.id))
            if running_work < min_work:
                min_work = running_work
                least_loaded = node

        return least_loaded
