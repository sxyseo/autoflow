"""
Autoflow Health Monitoring Module

Provides heartbeat-based health monitoring for distributed nodes.
Supports configurable intervals, automatic failure detection, and
health statistics tracking.

Usage:
    from autoflow.coordination.health import HealthMonitor, HealthConfig
    from autoflow.coordination.registry import NodeRegistry

    # Create health monitor with custom config
    registry = NodeRegistry()
    config = HealthConfig(heartbeat_interval=30, timeout_threshold=90)
    monitor = HealthMonitor(registry=registry, config=config)

    # Start monitoring
    await monitor.start()

    # Check health status
    status = await monitor.check_health("node-001")
    print(f"Node health: {status}")

    # Stop monitoring
    await monitor.stop()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.coordination.balancer import LoadBalancer
from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry
from autoflow.coordination.work_queue import (
    DistributedWorkQueue,
    WorkItemStatus,
)


class HealthStatus(str, Enum):
    """Health status of a node."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheckError(Exception):
    """Exception raised for health check errors."""

    def __init__(self, message: str, node_id: Optional[str] = None):
        self.node_id = node_id
        super().__init__(message)


@dataclass
class HealthConfig:
    """
    Configuration for health monitoring.

    Attributes:
        heartbeat_interval: Seconds between heartbeat checks (default: 30)
        timeout_threshold: Seconds before marking node as unhealthy (default: 90)
        degraded_threshold: Seconds before marking node as degraded (default: 60)
        check_timeout: Timeout for individual health checks (default: 5)
        max_consecutive_failures: Failures before marking unhealthy (default: 3)
        enable_auto_recovery: Allow nodes to recover after failures (default: True)
        recovery_threshold: Successes needed to recover (default: 2)

    Example:
        >>> config = HealthConfig(
        ...     heartbeat_interval=30,
        ...     timeout_threshold=90
        ... )
        >>> monitor = HealthMonitor(config=config)
    """

    heartbeat_interval: int = 30
    timeout_threshold: int = 90
    degraded_threshold: int = 60
    check_timeout: int = 5
    max_consecutive_failures: int = 3
    enable_auto_recovery: bool = True
    recovery_threshold: int = 2


class NodeHealthInfo(BaseModel):
    """
    Health information for a specific node.

    Attributes:
        node_id: Node identifier
        status: Current health status
        last_heartbeat: Timestamp of last successful heartbeat
        last_check: Timestamp of last health check
        consecutive_failures: Number of consecutive failed checks
        consecutive_successes: Number of consecutive successful checks
        total_checks: Total number of health checks performed
        total_failures: Total number of failed checks
        average_latency_ms: Average heartbeat latency in milliseconds
        is_monitored: Whether this node is actively monitored

    Example:
        >>> info = NodeHealthInfo(node_id="node-001")
        >>> info.record_check(success=True, latency_ms=45)
        >>> print(info.consecutive_failures)
        0
    """

    node_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_heartbeat: Optional[datetime] = None
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_checks: int = 0
    total_failures: int = 0
    average_latency_ms: float = 0.0
    is_monitored: bool = True

    def record_check(
        self,
        success: bool,
        latency_ms: Optional[float] = None,
    ) -> None:
        """
        Record a health check result.

        Args:
            success: Whether the check was successful
            latency_ms: Optional latency in milliseconds

        Example:
            >>> info.record_check(success=True, latency_ms=45)
        """
        self.last_check = datetime.utcnow()
        self.total_checks += 1

        if success:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.last_heartbeat = datetime.utcnow()

            # Update average latency
            if latency_ms is not None:
                if self.total_checks == 1:
                    self.average_latency_ms = latency_ms
                else:
                    # Exponential moving average
                    alpha = 0.3
                    self.average_latency_ms = (
                        alpha * latency_ms
                        + (1 - alpha) * self.average_latency_ms
                    )
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.total_failures += 1

    def update_status(self, config: HealthConfig) -> HealthStatus:
        """
        Update health status based on check history.

        Args:
            config: Health configuration

        Returns:
            Updated health status

        Example:
            >>> status = info.update_status(config)
        """
        # Check if node is unhealthy due to consecutive failures
        if self.consecutive_failures >= config.max_consecutive_failures:
            self.status = HealthStatus.UNHEALTHY
            return self.status

        # Check if node is degraded due to missed heartbeats
        if self.last_heartbeat:
            elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
            if elapsed > config.timeout_threshold:
                self.status = HealthStatus.UNHEALTHY
                return self.status
            elif elapsed > config.degraded_threshold:
                self.status = HealthStatus.DEGRADED
                return self.status

        # Check if node has recovered
        if (
            config.enable_auto_recovery
            and self.status == HealthStatus.UNHEALTHY
            and self.consecutive_successes >= config.recovery_threshold
        ):
            self.status = HealthStatus.HEALTHY
            return self.status

        # Default to healthy if we have recent successful checks
        if self.consecutive_successes > 0:
            self.status = HealthStatus.HEALTHY
        else:
            self.status = HealthStatus.UNKNOWN

        return self.status


class HealthMonitorStats(BaseModel):
    """
    Statistics about health monitoring operations.

    Attributes:
        total_checks: Total health checks performed
        successful_checks: Total successful checks
        failed_checks: Total failed checks
        healthy_nodes: Number of healthy nodes
        degraded_nodes: Number of degraded nodes
        unhealthy_nodes: Number of unhealthy nodes
        unknown_nodes: Number of nodes with unknown status
        average_latency_ms: Average latency across all checks
        uptime_seconds: Monitor uptime in seconds
        started_at: When monitoring started
        last_check_at: When last check was performed

    Example:
        >>> stats = monitor.get_stats()
        >>> print(f"Healthy nodes: {stats.healthy_nodes}")
    """

    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    healthy_nodes: int = 0
    degraded_nodes: int = 0
    unhealthy_nodes: int = 0
    unknown_nodes: int = 0
    average_latency_ms: float = 0.0
    uptime_seconds: float = 0.0
    started_at: Optional[datetime] = None
    last_check_at: Optional[datetime] = None

    def success_rate(self) -> float:
        """
        Calculate the success rate of health checks.

        Returns:
            Success rate as a percentage (0-100)

        Example:
            >>> rate = stats.success_rate()
            >>> print(f"Success rate: {rate}%")
        """
        if self.total_checks == 0:
            return 0.0
        return (self.successful_checks / self.total_checks) * 100


class HealthMonitor:
    """
    Monitors health of distributed nodes using heartbeats.

    The HealthMonitor tracks node health through periodic heartbeat checks,
    automatically detecting failures and status changes. It integrates with
    NodeRegistry to monitor all registered nodes and maintains health statistics.

    Example:
        >>> registry = NodeRegistry()
        >>> monitor = HealthMonitor(registry=registry)
        >>>
        >>> # Start monitoring
        >>> await monitor.start()
        >>>
        >>> # Check a specific node
        >>> status = await monitor.check_health("node-001")
        >>>
        >>> # Get overall statistics
        >>> stats = monitor.get_stats()
        >>>
        >>> # Stop monitoring
        >>> await monitor.stop()

    Attributes:
        registry: NodeRegistry instance
        config: Health configuration
        node_health: Dictionary of node health information
        is_running: Whether monitoring is active
        stats: Health monitoring statistics
    """

    def __init__(
        self,
        registry: Optional[NodeRegistry] = None,
        config: Optional[HealthConfig] = None,
        work_queue: Optional[DistributedWorkQueue] = None,
        load_balancer: Optional[LoadBalancer] = None,
    ) -> None:
        """
        Initialize the HealthMonitor.

        Args:
            registry: NodeRegistry instance (creates new if None)
            config: Health configuration (uses defaults if None)
            work_queue: Optional DistributedWorkQueue for failover operations
            load_balancer: Optional LoadBalancer for selecting replacement nodes

        Example:
            >>> monitor = HealthMonitor()
            >>> # or with custom config
            >>> config = HealthConfig(heartbeat_interval=60)
            >>> monitor = HealthMonitor(config=config)
        """
        self.registry = registry or NodeRegistry()
        self.config = config or HealthConfig()
        self.node_health: dict[str, NodeHealthInfo] = {}
        self.is_running = False
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self.stats = HealthMonitorStats()
        self.work_queue = work_queue
        self.load_balancer = load_balancer

    async def start(self) -> None:
        """
        Start the health monitoring loop.

        Begins periodic heartbeat checks on all monitored nodes.
        Runs in the background until stop() is called.

        Example:
            >>> await monitor.start()
        """
        if self.is_running:
            return

        self.is_running = True
        self.stats.started_at = datetime.utcnow()
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """
        Stop the health monitoring loop.

        Stops periodic heartbeat checks and cleans up resources.

        Example:
            >>> await monitor.stop()
        """
        self.is_running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    async def check_health(
        self,
        node_id: str,
        timeout: Optional[int] = None,
    ) -> HealthStatus:
        """
        Check the health of a specific node.

        Performs a health check on the specified node and updates
        its health information.

        Args:
            node_id: Node to check
            timeout: Optional timeout override (defaults to config.check_timeout)

        Returns:
            Current health status of the node

        Raises:
            HealthCheckError: If node not found or check fails

        Example:
            >>> status = await monitor.check_health("node-001")
            >>> if status == HealthStatus.UNHEALTHY:
            ...     print("Node is unhealthy!")
        """
        node = self.registry.lookup(node_id)
        if not node:
            raise HealthCheckError(
                f"Node not found: {node_id}",
                node_id=node_id,
            )

        check_timeout = timeout or self.config.check_timeout
        health_info = self._get_or_create_health_info(node_id)

        try:
            # Perform health check with timeout
            start_time = datetime.utcnow()
            await asyncio.wait_for(
                self._perform_health_check(node),
                timeout=check_timeout,
            )
            end_time = datetime.utcnow()

            # Calculate latency
            latency_ms = (end_time - start_time).total_seconds() * 1000

            # Record successful check
            health_info.record_check(success=True, latency_ms=latency_ms)
            self.stats.successful_checks += 1

        except asyncio.TimeoutError:
            # Record failed check due to timeout
            health_info.record_check(success=False)
            self.stats.failed_checks += 1
            raise HealthCheckError(
                f"Health check timeout for node: {node_id}",
                node_id=node_id,
            )
        except Exception as e:
            # Record failed check due to error
            health_info.record_check(success=False)
            self.stats.failed_checks += 1
            raise HealthCheckError(
                f"Health check failed for node {node_id}: {e}",
                node_id=node_id,
            )
        finally:
            # Update total checks
            self.stats.total_checks += 1
            self.stats.last_check_at = datetime.utcnow()

            # Update health status
            health_info.update_status(self.config)

            # Update node status in registry
            await self._update_node_status(node_id, health_info)

        return health_info.status

    async def check_all_nodes(self) -> dict[str, HealthStatus]:
        """
        Check health of all monitored nodes.

        Performs health checks on all nodes in the registry.

        Returns:
            Dictionary mapping node IDs to their health status

        Example:
            >>> statuses = await monitor.check_all_nodes()
            >>> for node_id, status in statuses.items():
            ...     print(f"{node_id}: {status}")
        """
        nodes = self.registry.list_nodes()
        results: dict[str, HealthStatus] = {}

        # Run checks in parallel
        tasks = [
            self.check_health(node.id)
            for node in nodes
            if node.status != NodeStatus.OFFLINE
        ]

        # Wait for all checks to complete
        completed, _ = await asyncio.wait(tasks, timeout=60)

        for task in completed:
            try:
                # Get node_id from task - we need to track this
                # For now, we'll collect results differently
                result = task.result()
                # We need to map results back to nodes
                # This is a simplified version
            except Exception:
                # Failed checks are already recorded in check_health
                pass

        # Return current health status for all nodes
        for node in nodes:
            health_info = self.node_health.get(node.id)
            if health_info:
                results[node.id] = health_info.status
            else:
                results[node.id] = HealthStatus.UNKNOWN

        return results

    def get_health_info(self, node_id: str) -> Optional[NodeHealthInfo]:
        """
        Get health information for a specific node.

        Args:
            node_id: Node identifier

        Returns:
            NodeHealthInfo if found, None otherwise

        Example:
            >>> info = monitor.get_health_info("node-001")
            >>> if info:
            ...     print(f"Status: {info.status}")
        """
        return self.node_health.get(node_id)

    def get_stats(self) -> HealthMonitorStats:
        """
        Get health monitoring statistics.

        Returns:
            Current monitoring statistics

        Example:
            >>> stats = monitor.get_stats()
            >>> print(f"Success rate: {stats.success_rate()}%")
        """
        # Update uptime
        if self.stats.started_at:
            self.stats.uptime_seconds = (
                datetime.utcnow() - self.stats.started_at
            ).total_seconds()

        # Update node counts
        healthy = 0
        degraded = 0
        unhealthy = 0
        unknown = 0

        for health_info in self.node_health.values():
            if health_info.status == HealthStatus.HEALTHY:
                healthy += 1
            elif health_info.status == HealthStatus.DEGRADED:
                degraded += 1
            elif health_info.status == HealthStatus.UNHEALTHY:
                unhealthy += 1
            else:
                unknown += 1

        self.stats.healthy_nodes = healthy
        self.stats.degraded_nodes = degraded
        self.stats.unhealthy_nodes = unhealthy
        self.stats.unknown_nodes = unknown

        return self.stats

    async def _monitor_loop(self) -> None:
        """Internal monitoring loop."""
        while self.is_running:
            try:
                # Check all nodes
                await self.check_all_nodes()

                # Wait for next interval
                await asyncio.sleep(self.config.heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue monitoring
                await asyncio.sleep(self.config.heartbeat_interval)

    async def _perform_health_check(self, node: Node) -> None:
        """
        Perform actual health check on a node.

        This is a placeholder that can be extended with actual
        health check logic (e.g., HTTP ping, RPC call, etc.).

        Args:
            node: Node to check

        Raises:
            Exception: If health check fails
        """
        # For now, just check if node is marked as online
        # In production, this would make an actual HTTP/RPC call
        if not node.is_online(timeout_seconds=self.config.timeout_threshold):
            raise Exception(f"Node {node.id} is not online")

    async def _update_node_status(
        self,
        node_id: str,
        health_info: NodeHealthInfo,
    ) -> None:
        """
        Update node status in registry based on health.

        Args:
            node_id: Node identifier
            health_info: Health information
        """
        node = self.registry.lookup(node_id)
        if not node:
            return

        # Map health status to node status
        if health_info.status == HealthStatus.HEALTHY:
            new_status = NodeStatus.ONLINE
        elif health_info.status == HealthStatus.DEGRADED:
            new_status = NodeStatus.BUSY
        elif health_info.status == HealthStatus.UNHEALTHY:
            new_status = NodeStatus.UNHEALTHY
        else:
            new_status = NodeStatus.OFFLINE

        # Update if status changed
        if node.status != new_status:
            self.registry.update_node_status(node_id, new_status)

    def _get_or_create_health_info(self, node_id: str) -> NodeHealthInfo:
        """
        Get or create health information for a node.

        Args:
            node_id: Node identifier

        Returns:
            NodeHealthInfo instance
        """
        if node_id not in self.node_health:
            self.node_health[node_id] = NodeHealthInfo(node_id=node_id)
        return self.node_health[node_id]

    async def detect_failures(
        self,
        force_check: bool = False,
    ) -> dict[str, NodeHealthInfo]:
        """
        Detect node failures and update node status accordingly.

        Scans all monitored nodes to detect failures based on health check
        history and heartbeat timestamps. Nodes that have exceeded failure
        thresholds or have not been seen recently are marked as failed.

        This method can be called proactively to check for failures outside
        the regular monitoring loop, or as part of the monitoring process.

        Args:
            force_check: If True, perform health checks on all nodes before
                        detecting failures. If False, use existing health data.

        Returns:
            Dictionary mapping node IDs to their NodeHealthInfo for all
            nodes detected as failed or unhealthy.

        Example:
            >>> failures = await monitor.detect_failures()
            >>> for node_id, health_info in failures.items():
            ...     print(f"Node {node_id}: {health_info.status}")
        """
        # Perform fresh health checks if requested
        if force_check:
            await self.check_all_nodes()

        failed_nodes: dict[str, NodeHealthInfo] = {}

        # Check all registered nodes
        nodes = self.registry.list_nodes()
        for node in nodes:
            health_info = self._get_or_create_health_info(node.id)

            # Update health status based on current state
            old_status = health_info.status
            new_status = health_info.update_status(self.config)

            # Check if node has failed or is unhealthy
            if new_status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED):
                failed_nodes[node.id] = health_info

                # Update node status in registry if it changed
                if old_status != new_status:
                    await self._update_node_status(node.id, health_info)

            # Also check nodes with no recent heartbeat
            if health_info.last_heartbeat:
                elapsed = (
                    datetime.utcnow() - health_info.last_heartbeat
                ).total_seconds()
                if elapsed > self.config.timeout_threshold:
                    health_info.status = HealthStatus.UNHEALTHY
                    failed_nodes[node.id] = health_info
                    await self._update_node_status(node.id, health_info)

        return failed_nodes

    async def get_failed_nodes(
        self,
        include_degraded: bool = False,
    ) -> list[str]:
        """
        Get list of node IDs that have failed or are unhealthy.

        A convenience method that returns just the node IDs without
        the full health information.

        Args:
            include_degraded: If True, include degraded nodes in addition
                            to unhealthy nodes. Defaults to False.

        Returns:
            List of node IDs that have failed or are unhealthy.

        Example:
            >>> failed = await monitor.get_failed_nodes()
            >>> if failed:
            ...     print(f"Failed nodes: {', '.join(failed)}")
        """
        failures = await self.detect_failures(force_check=False)

        if include_degraded:
            return list(failures.keys())

        # Filter to only unhealthy nodes
        return [
            node_id
            for node_id, health_info in failures.items()
            if health_info.status == HealthStatus.UNHEALTHY
        ]

    async def handle_failover(
        self,
        failed_node_ids: Optional[list[str]] = None,
        force_check: bool = True,
    ) -> dict[str, list[str]]:
        """
        Handle failover by reassigning work from failed nodes to healthy nodes.

        When nodes fail, their assigned work items need to be reassigned to
        healthy nodes to ensure work continues. This method detects failures,
        finds work assigned to failed nodes, and reassigns it to healthy nodes
        using the load balancer.

        Args:
            failed_node_ids: Optional list of specific failed node IDs to handle.
                           If None, detects failures automatically.
            force_check: If True, perform health checks before failover. Ignored
                        if failed_node_ids is provided.

        Returns:
            Dictionary mapping old node IDs to lists of reassigned work item IDs

        Raises:
            HealthCheckError: If work queue or load balancer not configured

        Example:
            >>> # Automatic failover for detected failures
            >>> reassigned = await monitor.handle_failover()
            >>> for old_node, work_ids in reassigned.items():
            ...     print(f"Reassigned {len(work_ids)} items from {old_node}")

            >>> # Manual failover for specific nodes
            >>> reassigned = await monitor.handle_failover(
            ...     failed_node_ids=["node-001"]
            ... )
        """
        if not self.work_queue:
            raise HealthCheckError(
                "Work queue not configured. Cannot perform failover."
            )

        if not self.load_balancer:
            raise HealthCheckError(
                "Load balancer not configured. Cannot perform failover."
            )

        # Detect failures if not provided
        if failed_node_ids is None:
            failures = await self.detect_failures(force_check=force_check)
            failed_node_ids = list(failures.keys())

        if not failed_node_ids:
            return {}

        reassigned_work: dict[str, list[str]] = {}

        # Handle failover for each failed node
        for failed_node_id in failed_node_ids:
            # Get work items assigned to the failed node
            # Only reassign work that is ASSIGNED or RUNNING
            work_items = self.work_queue.get_work_for_node(
                failed_node_id,
                status_filter=None,  # Get all work for this node
            )

            # Filter to only active work (ASSIGNED or RUNNING)
            active_work = [
                w
                for w in work_items
                if w.status in (WorkItemStatus.ASSIGNED, WorkItemStatus.RUNNING)
            ]

            if not active_work:
                reassigned_work[failed_node_id] = []
                continue

            # Get all available nodes except the failed one
            available_nodes = [
                node
                for node in self.registry.get_available_nodes()
                if node.id != failed_node_id
            ]

            if not available_nodes:
                # No healthy nodes available for failover
                reassigned_work[failed_node_id] = []
                continue

            # Select a replacement node using the load balancer
            # We manually filter nodes to exclude the failed node
            replacement_node = self.load_balancer.select_node(
                exclude_busy=True,
            )

            # Verify the selected node is not the failed node
            if not replacement_node or replacement_node.id == failed_node_id:
                # Manually select the first available node as fallback
                replacement_node = available_nodes[0]

            if not replacement_node:
                # No healthy nodes available for failover
                reassigned_work[failed_node_id] = []
                continue

            # Reassign all work from failed node to replacement node
            reassigned_ids = []
            for work in active_work:
                result = self.work_queue.reassign_work(
                    work.id,
                    replacement_node.id,
                )
                if result:
                    reassigned_ids.append(work.id)

                    # Update load balancer assignment records
                    # Mark old assignment as failed
                    self.load_balancer.complete_assignment(
                        work.id,
                        success=False,
                    )
                    # Record new assignment
                    self.load_balancer.record_assignment(
                        replacement_node.id,
                        work_id=work.id,
                    )

            reassigned_work[failed_node_id] = reassigned_ids

        return reassigned_work

    async def auto_failover(
        self,
        check_interval: Optional[int] = None,
    ) -> None:
        """
        Continuously monitor for failures and automatically handle failover.

        Runs in the background, periodically checking for failed nodes and
        reassigning their work to healthy nodes. Stops when the monitor
        is stopped.

        Args:
            check_interval: Seconds between failover checks. Defaults to
                          config.heartbeat_interval if not specified.

        Example:
            >>> # Start auto-failover
            >>> await monitor.start()
            >>> asyncio.create_task(monitor.auto_failover())
            >>>
            >>> # Later, stop monitoring
            >>> await monitor.stop()
        """
        interval = check_interval or self.config.heartbeat_interval

        while self.is_running:
            try:
                # Handle failover for any detected failures
                await self.handle_failover(force_check=True)

                # Wait for next check
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue auto-failover
                await asyncio.sleep(interval)
