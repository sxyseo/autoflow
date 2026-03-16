"""
Autoflow Load Balancer Module

Provides load balancing capabilities for distributing work across nodes
in a distributed cluster. Supports multiple strategies including least-loaded,
round-robin, and weighted random selection based on node capacity and health.

Usage:
    from autoflow.coordination.balancer import LoadBalancer, LoadBalancingStrategy
    from autoflow.coordination.registry import NodeRegistry

    # Create a load balancer
    registry = NodeRegistry()
    balancer = LoadBalancer(registry)

    # Select a node for work assignment
    node = balancer.select_node(capability="claude-code")
    if node:
        print(f"Selected {node.id} for work assignment")

    # Track work assignment
    balancer.record_assignment(node.id, work_id="work-001")
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry


class LoadBalancingStrategy(str, Enum):
    """Load balancing strategy for node selection."""

    LEAST_LOADED = "least_loaded"  # Select node with least current work
    ROUND_ROBIN = "round_robin"  # Cycle through nodes sequentially
    RANDOM = "random"  # Random selection from available nodes
    WEIGHTED = "weighted"  # Weight by capacity and health score


class BalancerError(Exception):
    """Exception raised for load balancer errors."""

    def __init__(self, message: str, node_id: Optional[str] = None):
        self.node_id = node_id
        super().__init__(message)


@dataclass
class AssignmentRecord:
    """
    Record of a work assignment to a node.

    Attributes:
        assignment_id: Unique assignment identifier
        node_id: ID of the node work was assigned to
        work_id: ID of the work item
        assigned_at: When the work was assigned
        completed_at: When the work was completed (None if still running)
        status: Current assignment status

    Example:
        >>> record = AssignmentRecord(
        ...     node_id="node-001",
        ...     work_id="work-001"
        ... )
        >>> record.mark_completed()
    """

    assignment_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    node_id: str = ""
    work_id: str = ""
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "assigned"  # assigned, completed, failed

    def mark_completed(self, status: str = "completed") -> None:
        """
        Mark the assignment as completed.

        Args:
            status: Final status (completed or failed)

        Example:
            >>> record.mark_completed()
        """
        self.status = status
        self.completed_at = datetime.utcnow()

    def duration_seconds(self) -> Optional[float]:
        """
        Calculate the duration of the assignment.

        Returns:
            Duration in seconds, or None if not completed

        Example:
            >>> if record.completed_at:
            ...     print(f"Duration: {record.duration_seconds()}s")
        """
        if self.completed_at:
            return (self.completed_at - self.assigned_at).total_seconds()
        return None


class LoadBalancerStats(BaseModel):
    """
    Statistics about load balancer operations.

    Attributes:
        total_selections: Total number of node selections
        total_assignments: Total number of work assignments
        completed_assignments: Number of completed assignments
        failed_assignments: Number of failed assignments
        strategy: Current load balancing strategy
        last_selection_at: Timestamp of last node selection
        last_assignment_at: Timestamp of last work assignment

    Example:
        >>> stats = LoadBalancerStats(total_selections=100, strategy="least_loaded")
        >>> print(f"Success rate: {stats.success_rate():.1f}%")
    """

    total_selections: int = 0
    total_assignments: int = 0
    completed_assignments: int = 0
    failed_assignments: int = 0
    strategy: str = LoadBalancingStrategy.LEAST_LOADED.value
    last_selection_at: Optional[datetime] = None
    last_assignment_at: Optional[datetime] = None

    def success_rate(self) -> float:
        """
        Calculate the success rate of assignments.

        Returns:
            Success rate as percentage (0-100)

        Example:
            >>> stats = LoadBalancerStats(
            ...     total_assignments=100,
            ...     failed_assignments=5
            ... )
            >>> print(f"{stats.success_rate():.1f}% success rate")
        """
        if self.total_assignments == 0:
            return 100.0
        return ((self.total_assignments - self.failed_assignments) / self.total_assignments) * 100


class LoadBalancer:
    """
    Load balancer for distributing work across distributed nodes.

    The LoadBalancer selects nodes based on their current load, health status,
    and capabilities using various strategies. It tracks work assignments and
    provides statistics on load balancing performance.

    Strategies:
    - LEAST_LOADED: Select node with fewest active assignments
    - ROUND_ROBIN: Cycle through available nodes
    - RANDOM: Random selection from available nodes
    - WEIGHTED: Weight selection by capacity and health score

    Attributes:
        registry: NodeRegistry instance for node lookups
        strategy: Current load balancing strategy
        assignment_history: List of assignment records
        round_robin_index: Current index for round-robin selection

    Example:
        >>> registry = NodeRegistry()
        >>> balancer = LoadBalancer(
        ...     registry=registry,
        ...     strategy=LoadBalancingStrategy.LEAST_LOADED
        ... )
        >>>
        >>> # Select a node for work
        >>> node = balancer.select_node(capability="claude-code")
        >>> if node:
        ...     balancer.record_assignment(node.id, work_id="work-001")
    """

    DEFAULT_TIMEOUT_SECONDS = 30  # Heartbeat timeout for node health

    def __init__(
        self,
        registry: Optional[NodeRegistry] = None,
        strategy: LoadBalancingStrategy = LoadBalancingStrategy.LEAST_LOADED,
    ):
        """
        Initialize the LoadBalancer.

        Args:
            registry: Optional NodeRegistry instance for node lookups.
                     If None, creates a new in-memory registry.
            strategy: Load balancing strategy to use

        Example:
            >>> registry = NodeRegistry()
            >>> balancer = LoadBalancer(
            ...     registry=registry,
            ...     strategy=LoadBalancingStrategy.ROUND_ROBIN
            ... )
        """
        self._registry = registry or NodeRegistry()
        self._strategy = strategy
        self._assignment_history: list[AssignmentRecord] = []
        self._round_robin_index = 0
        self._stats = LoadBalancerStats(
            strategy=strategy.value,
        )

    @property
    def registry(self) -> NodeRegistry:
        """Get the node registry."""
        return self._registry

    @property
    def strategy(self) -> LoadBalancingStrategy:
        """Get the current load balancing strategy."""
        return self._strategy

    @property
    def stats(self) -> LoadBalancerStats:
        """Get load balancer statistics."""
        return self._stats

    def set_strategy(self, strategy: LoadBalancingStrategy) -> None:
        """
        Change the load balancing strategy.

        Args:
            strategy: New strategy to use

        Example:
            >>> balancer.set_strategy(LoadBalancingStrategy.RANDOM)
        """
        self._strategy = strategy
        self._stats.strategy = strategy.value

    def select_node(
        self,
        capability: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        exclude_busy: bool = True,
    ) -> Optional[Node]:
        """
        Select a node for work assignment using the configured strategy.

        Args:
            capability: Optional capability filter - only consider nodes
                       with this capability
            timeout_seconds: Override default heartbeat timeout
            exclude_busy: If True, exclude nodes with BUSY status

        Returns:
            Selected node, or None if no suitable node available

        Raises:
            BalancerError: If node selection fails

        Example:
            >>> # Select least-loaded node with claude-code capability
            >>> node = balancer.select_node(capability="claude-code")
            >>> if node:
            ...     print(f"Selected {node.id}")
        """
        timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS

        try:
            # Get available nodes
            if exclude_busy:
                available_nodes = self._registry.get_available_nodes(
                    capability=capability
                )
                # Filter by heartbeat timeout
                available_nodes = [
                    n
                    for n in available_nodes
                    if n.is_online(timeout_seconds=timeout)
                ]
            else:
                available_nodes = self._registry.get_online_nodes(
                    timeout_seconds=timeout
                )
                if capability:
                    available_nodes = [
                        n for n in available_nodes if n.has_capability(capability)
                    ]

            if not available_nodes:
                return None

            # Select node based on strategy
            selected_node: Optional[Node] = None

            if self._strategy == LoadBalancingStrategy.LEAST_LOADED:
                selected_node = self._select_least_loaded(available_nodes)
            elif self._strategy == LoadBalancingStrategy.ROUND_ROBIN:
                selected_node = self._select_round_robin(available_nodes)
            elif self._strategy == LoadBalancingStrategy.RANDOM:
                selected_node = self._select_random(available_nodes)
            elif self._strategy == LoadBalancingStrategy.WEIGHTED:
                selected_node = self._select_weighted(available_nodes)
            else:
                # Fallback to least-loaded
                selected_node = self._select_least_loaded(available_nodes)

            # Update statistics
            if selected_node:
                self._stats.total_selections += 1
                self._stats.last_selection_at = datetime.utcnow()

            return selected_node

        except Exception as e:
            raise BalancerError(f"Node selection failed: {e}") from e

    def _select_least_loaded(self, nodes: list[Node]) -> Optional[Node]:
        """
        Select node with least current work load.

        Args:
            nodes: List of candidate nodes

        Returns:
            Node with fewest active assignments

        Example:
            >>> node = balancer._select_least_loaded(available_nodes)
        """
        if not nodes:
            return None

        # Count active assignments for each node
        node_loads: dict[str, int] = {}
        for node in nodes:
            active_count = sum(
                1
                for record in self._assignment_history
                if record.node_id == node.id and record.status == "assigned"
            )
            node_loads[node.id] = active_count

        # Find node with minimum load
        least_loaded = min(nodes, key=lambda n: node_loads.get(n.id, 0))

        return least_loaded

    def _select_round_robin(self, nodes: list[Node]) -> Optional[Node]:
        """
        Select node using round-robin strategy.

        Args:
            nodes: List of candidate nodes

        Returns:
            Next node in round-robin sequence

        Example:
            >>> node = balancer._select_round_robin(available_nodes)
        """
        if not nodes:
            return None

        # Ensure index is within bounds
        if self._round_robin_index >= len(nodes):
            self._round_robin_index = 0

        selected = nodes[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(nodes)

        return selected

    def _select_random(self, nodes: list[Node]) -> Optional[Node]:
        """
        Select node randomly from available nodes.

        Args:
            nodes: List of candidate nodes

        Returns:
            Randomly selected node

        Example:
            >>> node = balancer._select_random(available_nodes)
        """
        if not nodes:
            return None

        return random.choice(nodes)

    def _select_weighted(self, nodes: list[Node]) -> Optional[Node]:
        """
        Select node using weighted random selection based on health and load.

        Nodes with better health and lower load get higher weights.

        Args:
            nodes: List of candidate nodes

        Returns:
            Weighted randomly selected node

        Example:
            >>> node = balancer._select_weighted(available_nodes)
        """
        if not nodes:
            return None

        # Calculate weights for each node
        weights: list[float] = []
        for node in nodes:
            # Base weight
            weight = 1.0

            # Health bonus: nodes recently seen get higher weight
            seconds_since_seen = (datetime.utcnow() - node.last_seen).total_seconds()
            if seconds_since_seen < 10:
                weight *= 2.0  # Very healthy
            elif seconds_since_seen < 30:
                weight *= 1.5  # Healthy
            elif seconds_since_seen < 60:
                weight *= 1.0  # OK
            else:
                weight *= 0.5  # Degraded

            # Load penalty: nodes with more assignments get lower weight
            active_count = sum(
                1
                for record in self._assignment_history
                if record.node_id == node.id and record.status == "assigned"
            )
            weight /= max(1, active_count)

            weights.append(weight)

        # Weighted random selection
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(nodes)

        rand = random.uniform(0, total_weight)
        cumulative = 0.0
        for node, weight in zip(nodes, weights):
            cumulative += weight
            if rand <= cumulative:
                return node

        # Fallback to last node if floating point issues
        return nodes[-1]

    def record_assignment(
        self,
        node_id: str,
        work_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AssignmentRecord:
        """
        Record a work assignment to a node.

        Args:
            node_id: ID of the node receiving the assignment
            work_id: ID of the work item being assigned
            metadata: Optional metadata for the assignment

        Returns:
            AssignmentRecord created for this assignment

        Example:
            >>> record = balancer.record_assignment(
            ...     node_id="node-001",
            ...     work_id="work-001"
            ... )
        """
        record = AssignmentRecord(
            node_id=node_id,
            work_id=work_id,
        )

        self._assignment_history.append(record)
        self._stats.total_assignments += 1
        self._stats.last_assignment_at = datetime.utcnow()

        return record

    def complete_assignment(
        self,
        work_id: str,
        success: bool = True,
    ) -> bool:
        """
        Mark a work assignment as completed.

        Args:
            work_id: ID of the work item to complete
            success: Whether the assignment completed successfully

        Returns:
            True if assignment was found and updated, False otherwise

        Example:
            >>> balancer.complete_assignment("work-001", success=True)
        """
        for record in reversed(self._assignment_history):
            if record.work_id == work_id and record.status == "assigned":
                status = "completed" if success else "failed"
                record.mark_completed(status=status)

                if success:
                    self._stats.completed_assignments += 1
                else:
                    self._stats.failed_assignments += 1

                return True

        return False

    def get_active_assignments(self, node_id: Optional[str] = None) -> list[AssignmentRecord]:
        """
        Get all active (uncompleted) assignments.

        Args:
            node_id: Optional node ID to filter by

        Returns:
            List of active assignment records

        Example:
            >>> active = balancer.get_active_assignments(node_id="node-001")
            >>> print(f"Node has {len(active)} active assignments")
        """
        active = [
            record
            for record in self._assignment_history
            if record.status == "assigned"
        ]

        if node_id:
            active = [r for r in active if r.node_id == node_id]

        return active

    def get_assignment_count(self, node_id: str) -> int:
        """
        Get the number of active assignments for a node.

        Args:
            node_id: ID of the node

        Returns:
            Number of active assignments

        Example:
            >>> count = balancer.get_assignment_count("node-001")
        """
        return len(self.get_active_assignments(node_id=node_id))

    def get_node_health_score(self, node_id: str) -> float:
        """
        Calculate a health score for a node (0.0 to 1.0).

        Health score considers:
        - How recently the node was seen
        - Current load (active assignments)
        - Success rate of past assignments

        Args:
            node_id: ID of the node

        Returns:
            Health score from 0.0 (unhealthy) to 1.0 (healthy)

        Example:
            >>> score = balancer.get_node_health_score("node-001")
            >>> print(f"Health: {score:.2f}")
        """
        node = self._registry.lookup(node_id)
        if not node:
            return 0.0

        score = 1.0

        # Heartbeat freshness
        seconds_since_seen = (datetime.utcnow() - node.last_seen).total_seconds()
        if seconds_since_seen > 60:
            score *= 0.5  # Old heartbeat
        elif seconds_since_seen > 30:
            score *= 0.8

        # Load penalty
        active_count = self.get_assignment_count(node_id)
        if active_count > 10:
            score *= 0.5  # Very loaded
        elif active_count > 5:
            score *= 0.7
        elif active_count > 2:
            score *= 0.9

        # Success rate
        node_assignments = [
            r for r in self._assignment_history if r.node_id == node_id
        ]
        if node_assignments:
            completed = [r for r in node_assignments if r.completed_at is not None]
            if completed:
                success_count = sum(1 for r in completed if r.status == "completed")
                success_rate = success_count / len(completed)
                score *= success_rate

        return max(0.0, min(1.0, score))

    def prune_history(self, keep_last: int = 1000) -> None:
        """
        Prune assignment history to keep only recent records.

        Args:
            keep_last: Number of most recent records to keep

        Example:
            >>> balancer.prune_history(keep_last=500)
        """
        if len(self._assignment_history) > keep_last:
            self._assignment_history = self._assignment_history[-keep_last:]

    def get_stats(self) -> LoadBalancerStats:
        """
        Get a copy of the current statistics.

        Returns:
            LoadBalancerStats with current statistics

        Example:
            >>> stats = balancer.get_stats()
            >>> print(f"Total selections: {stats.total_selections}")
        """
        return LoadBalancerStats.model_validate(self._stats)

    def clear_history(self) -> None:
        """
        Clear all assignment history.

        Example:
            >>> balancer.clear_history()
        """
        self._assignment_history.clear()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"LoadBalancer("
            f"strategy={self._strategy.value}, "
            f"assignments={self._stats.total_assignments}, "
            f"nodes={self._registry.get_node_count()})"
        )


def create_load_balancer(
    registry: Optional[NodeRegistry] = None,
    strategy: LoadBalancingStrategy = LoadBalancingStrategy.LEAST_LOADED,
) -> LoadBalancer:
    """
    Factory function to create a configured LoadBalancer.

    Args:
        registry: Optional NodeRegistry instance. If None, creates a new one.
        strategy: Load balancing strategy

    Returns:
        Configured LoadBalancer instance

    Example:
        >>> registry = NodeRegistry()
        >>> balancer = create_load_balancer(
        ...     registry=registry,
        ...     strategy=LoadBalancingStrategy.ROUND_ROBIN
        ... )
    """
    return LoadBalancer(registry=registry, strategy=strategy)
