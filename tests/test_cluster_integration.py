"""
Integration Tests for Multi-Node Cluster Coordination

Tests distributed execution across multiple nodes including:
- Cluster state management across nodes
- Work distribution and load balancing
- Node health monitoring and failover
- Work queue management with multiple nodes
- State synchronization and recovery

These tests use mocks to avoid requiring actual network services
or multiple physical machines.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.coordination.balancer import (
    AssignmentRecord,
    BalancerError,
    LoadBalancer,
    LoadBalancingStrategy,
)
from autoflow.coordination.cluster import (
    ClusterState,
    ClusterStatus,
    WorkItem,
    WorkItemStatus,
)
from autoflow.coordination.health import (
    HealthConfig,
    HealthMonitor,
    HealthStatus,
    NodeHealthInfo,
)
from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry, RegistryStats
from autoflow.coordination.work_queue import (
    DistributedWorkQueue,
    WorkItem as QueueWorkItem,
    WorkItemStatus as QueueWorkItemStatus,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_queue_dir(tmp_path: Path) -> Path:
    """Create a temporary queue directory."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    return queue_dir


@pytest.fixture
def sample_nodes() -> list[Node]:
    """Create sample nodes for testing."""
    return [
        Node(
            id="node-001",
            address="localhost:8001",
            capabilities=["claude-code", "test-runner"],
            status=NodeStatus.ONLINE,
        ),
        Node(
            id="node-002",
            address="localhost:8002",
            capabilities=["claude-code", "codex"],
            status=NodeStatus.ONLINE,
        ),
        Node(
            id="node-003",
            address="localhost:8003",
            capabilities=["test-runner", "linter"],
            status=NodeStatus.ONLINE,
        ),
        Node(
            id="node-004",
            address="localhost:8004",
            capabilities=["claude-code"],
            status=NodeStatus.OFFLINE,
        ),
    ]


@pytest.fixture
def node_registry(sample_nodes: list[Node]) -> NodeRegistry:
    """Create a node registry with sample nodes."""
    registry = NodeRegistry()
    for node in sample_nodes:
        registry.register(node)
    return registry


@pytest.fixture
def cluster_state(sample_nodes: list[Node]) -> ClusterState:
    """Create a cluster state with sample nodes."""
    cluster = ClusterState(cluster_id="test-cluster")
    for node in sample_nodes:
        cluster.add_node(node)
    return cluster


@pytest.fixture
def work_queue(temp_queue_dir: Path) -> DistributedWorkQueue:
    """Create a distributed work queue."""
    queue = DistributedWorkQueue(queue_dir=temp_queue_dir)
    queue.initialize()
    return queue


@pytest.fixture
def load_balancer(node_registry: NodeRegistry) -> LoadBalancer:
    """Create a load balancer."""
    return LoadBalancer(registry=node_registry)


# ============================================================================
# Multi-Node Cluster Setup Tests
# ============================================================================


class TestMultiNodeClusterSetup:
    """Tests for setting up and managing multi-node clusters."""

    def test_cluster_initialization(self, sample_nodes: list[Node]) -> None:
        """Test initializing a cluster with multiple nodes."""
        cluster = ClusterState(cluster_id="multi-node-cluster")

        # Add all nodes
        for node in sample_nodes:
            cluster.add_node(node)

        # Verify all nodes are present
        assert len(cluster.nodes) == 4
        assert cluster.get_node("node-001") is not None
        assert cluster.get_node("node-002") is not None
        assert cluster.get_node("node-003") is not None
        assert cluster.get_node("node-004") is not None

    def test_cluster_health_status(self, cluster_state: ClusterState) -> None:
        """Test cluster health status calculation."""
        # Update health status
        status = cluster_state.update_health_status(timeout_seconds=30)

        # Should be degraded because node-004 is offline
        assert status == ClusterStatus.DEGRADED

        # Get node counts
        counts = cluster_state.get_node_count()
        assert counts["online"] == 3
        assert counts["offline"] == 1

    def test_cluster_capacity_calculation(self, cluster_state: ClusterState) -> None:
        """Test available capacity calculation across nodes."""
        capacity = cluster_state.get_available_capacity()

        # Only online nodes should have capacity
        assert "node-001" in capacity
        assert "node-002" in capacity
        assert "node-003" in capacity
        assert "node-004" not in capacity  # Offline

    def test_find_least_loaded_node(self, cluster_state: ClusterState) -> None:
        """Test finding the least loaded node."""
        # Add some work to node-001
        work1 = WorkItem(
            id="work-001",
            task_id="task-001",
            assigned_node="node-001",
            status=WorkItemStatus.RUNNING,
        )
        work2 = WorkItem(
            id="work-002",
            task_id="task-002",
            assigned_node="node-001",
            status=WorkItemStatus.RUNNING,
        )
        cluster_state.add_work_item(work1)
        cluster_state.add_work_item(work2)

        # Find least loaded node
        node = cluster_state.find_least_loaded_node()

        # Should be node-002 or node-003 (0 work each)
        assert node is not None
        assert node.id in ["node-002", "node-003"]

    def test_find_least_loaded_node_with_capability(
        self,
        cluster_state: ClusterState,
    ) -> None:
        """Test finding least loaded node with specific capability."""
        # Find node with test-runner capability
        node = cluster_state.find_least_loaded_node(capability="test-runner")

        # Should be node-001 or node-003 (both have test-runner)
        assert node is not None
        assert node.id in ["node-001", "node-003"]
        assert node.has_capability("test-runner")


# ============================================================================
# Work Distribution Tests
# ============================================================================


class TestWorkDistribution:
    """Tests for distributing work across multiple nodes."""

    def test_assign_work_to_multiple_nodes(
        self,
        cluster_state: ClusterState,
    ) -> None:
        """Test assigning work to different nodes."""
        # Create work items
        work_items = [
            WorkItem(id="work-001", task_id="task-001", assigned_node="node-001"),
            WorkItem(id="work-002", task_id="task-002", assigned_node="node-002"),
            WorkItem(id="work-003", task_id="task-003", assigned_node="node-003"),
        ]

        # Add work to cluster
        for work in work_items:
            cluster_state.add_work_item(work)

        # Verify work distribution
        assert len(cluster_state.get_work_for_node("node-001")) == 1
        assert len(cluster_state.get_work_for_node("node-002")) == 1
        assert len(cluster_state.get_work_for_node("node-003")) == 1

    def test_get_pending_work(self, cluster_state: ClusterState) -> None:
        """Test getting pending work items."""
        # Add work items with different statuses
        work1 = WorkItem(
            id="work-001",
            task_id="task-001",
            assigned_node="node-001",
            status=WorkItemStatus.PENDING,
        )
        work2 = WorkItem(
            id="work-002",
            task_id="task-002",
            assigned_node="node-002",
            status=WorkItemStatus.RUNNING,
        )
        work3 = WorkItem(
            id="work-003",
            task_id="task-003",
            assigned_node="node-003",
            status=WorkItemStatus.PENDING,
        )

        cluster_state.add_work_item(work1)
        cluster_state.add_work_item(work2)
        cluster_state.add_work_item(work3)

        # Get pending work
        pending = cluster_state.get_pending_work()

        assert len(pending) == 2
        assert all(w.status in [WorkItemStatus.PENDING, WorkItemStatus.ASSIGNED] for w in pending)

    def test_get_running_work(self, cluster_state: ClusterState) -> None:
        """Test getting running work items."""
        # Add running work
        work1 = WorkItem(
            id="work-001",
            task_id="task-001",
            assigned_node="node-001",
            status=WorkItemStatus.RUNNING,
        )
        work2 = WorkItem(
            id="work-002",
            task_id="task-002",
            assigned_node="node-002",
            status=WorkItemStatus.RUNNING,
        )

        cluster_state.add_work_item(work1)
        cluster_state.add_work_item(work2)

        # Get running work
        running = cluster_state.get_running_work()

        assert len(running) == 2
        assert all(w.status == WorkItemStatus.RUNNING for w in running)

    def test_work_item_lifecycle(self, cluster_state: ClusterState) -> None:
        """Test complete work item lifecycle."""
        work = WorkItem(
            id="work-001",
            task_id="task-001",
            assigned_node="node-001",
            status=WorkItemStatus.PENDING,
        )

        cluster_state.add_work_item(work)

        # Start work
        work.start()
        assert work.status == WorkItemStatus.RUNNING
        assert work.started_at is not None

        # Complete work
        work.complete()
        assert work.status == WorkItemStatus.COMPLETED
        assert work.completed_at is not None
        duration = work.duration_seconds()
        assert duration is not None
        assert duration >= 0


# ============================================================================
# Load Balancing Tests
# ============================================================================


class TestLoadBalancing:
    """Tests for load balancing across nodes."""

    def test_least_loaded_strategy(self, load_balancer: LoadBalancer) -> None:
        """Test least-loaded load balancing strategy."""
        load_balancer.set_strategy(LoadBalancingStrategy.LEAST_LOADED)

        # Record some assignments
        load_balancer.record_assignment("node-001", "work-001")
        load_balancer.record_assignment("node-001", "work-002")
        load_balancer.record_assignment("node-002", "work-003")

        # Select node
        node = load_balancer.select_node()

        # Should prefer node-002 or node-003 (less loaded)
        assert node is not None
        assert node.id in ["node-002", "node-003"]

    def test_round_robin_strategy(self, load_balancer: LoadBalancer) -> None:
        """Test round-robin load balancing strategy."""
        load_balancer.set_strategy(LoadBalancingStrategy.ROUND_ROBIN)

        # Select nodes in sequence
        nodes_selected = []
        for _ in range(6):
            node = load_balancer.select_node()
            if node:
                nodes_selected.append(node.id)

        # Should cycle through online nodes
        assert len(set(nodes_selected)) > 1

    def test_random_strategy(self, load_balancer: LoadBalancer) -> None:
        """Test random load balancing strategy."""
        load_balancer.set_strategy(LoadBalancingStrategy.RANDOM)

        # Select multiple nodes
        nodes_selected = []
        for _ in range(10):
            node = load_balancer.select_node()
            if node:
                nodes_selected.append(node.id)

        # Should get a variety of nodes
        assert len(nodes_selected) > 0

    def test_capability_filtering(self, load_balancer: LoadBalancer) -> None:
        """Test filtering nodes by capability."""
        # Select node with specific capability
        node = load_balancer.select_node(capability="test-runner")

        assert node is not None
        assert node.has_capability("test-runner")

        # Verify it's one of the nodes with test-runner
        assert node.id in ["node-001", "node-003"]

    def test_assignment_tracking(self, load_balancer: LoadBalancer) -> None:
        """Test tracking work assignments."""
        # Record assignment
        record = load_balancer.record_assignment("node-001", "work-001")

        assert record.node_id == "node-001"
        assert record.work_id == "work-001"
        assert record.status == "assigned"

        # Check active assignments
        active = load_balancer.get_active_assignments("node-001")
        assert len(active) == 1

    def test_assignment_completion(self, load_balancer: LoadBalancer) -> None:
        """Test marking assignments as completed."""
        # Record assignment
        load_balancer.record_assignment("node-001", "work-001")

        # Complete it
        result = load_balancer.complete_assignment("work-001", success=True)

        assert result is True

        # Check stats
        stats = load_balancer.get_stats()
        assert stats.completed_assignments == 1
        assert stats.failed_assignments == 0

    def test_node_health_score(self, load_balancer: LoadBalancer) -> None:
        """Test calculating node health scores."""
        # Get health score for a node
        score = load_balancer.get_node_health_score("node-001")

        # Score should be between 0 and 1
        assert 0.0 <= score <= 1.0


# ============================================================================
# Node Failure and Failover Tests
# ============================================================================


class TestNodeFailureAndFailover:
    """Tests for handling node failures and failover."""

    def test_node_failure_detection(self, sample_nodes: list[Node]) -> None:
        """Test detecting failed nodes."""
        cluster = ClusterState(cluster_id="failover-test")
        for node in sample_nodes:
            cluster.add_node(node)

        # Simulate node failure by updating status
        node_001 = cluster.get_node("node-001")
        assert node_001 is not None
        node_001.status = NodeStatus.OFFLINE

        # Update health status
        status = cluster.update_health_status()

        # Cluster should be degraded
        assert status == ClusterStatus.DEGRADED

    def test_work_reassignment_on_failure(
        self,
        work_queue: DistributedWorkQueue,
        sample_nodes: list[Node],
    ) -> None:
        """Test reassigning work when a node fails."""
        # Create work items assigned to a node
        work1 = QueueWorkItem(
            id="work-001",
            task="Task 1",
            priority=5,
        )
        work1.assign_to("node-001")

        work2 = QueueWorkItem(
            id="work-002",
            task="Task 2",
            priority=5,
        )
        work2.assign_to("node-001")

        work_queue.enqueue(work1)
        work_queue.enqueue(work2)

        # Assign work
        work_queue.assign("work-001", "node-001")
        work_queue.assign("work-002", "node-001")

        # Reassign all work from node-001 to node-002
        reassigned = work_queue.reassign_all_work_for_node("node-001", "node-002")

        assert len(reassigned) == 2
        assert all(w.assigned_node == "node-002" for w in reassigned)

    def test_get_work_for_failed_node(
        self,
        work_queue: DistributedWorkQueue,
    ) -> None:
        """Test retrieving work for a failed node."""
        # Create and assign work
        work = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work_queue.enqueue(work)
        work_queue.assign("work-001", "node-001")

        # Get work for the node
        node_work = work_queue.get_work_for_node("node-001")

        assert len(node_work) == 1
        assert node_work[0].id == "work-001"

    def test_failover_to_healthy_node(
        self,
        node_registry: NodeRegistry,
    ) -> None:
        """Test failing over to a healthy node."""
        balancer = LoadBalancer(registry=node_registry)

        # Select a node
        node1 = balancer.select_node(capability="claude-code")
        assert node1 is not None

        # Simulate failure of selected node
        node1.status = NodeStatus.OFFLINE
        node_registry.register(node1)

        # Select again - should get a different node
        node2 = balancer.select_node(capability="claude-code")
        assert node2 is not None
        assert node2.id != node1.id


# ============================================================================
# Work Queue Management Tests
# ============================================================================


class TestWorkQueueManagement:
    """Tests for managing distributed work queue."""

    def test_enqueue_and_dequeue(self, work_queue: DistributedWorkQueue) -> None:
        """Test enqueuing and dequeuing work."""
        # Create work items
        work1 = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work2 = QueueWorkItem(id="work-002", task="Task 2", priority=8)
        work3 = QueueWorkItem(id="work-003", task="Task 3", priority=3)

        # Enqueue
        work_queue.enqueue(work1)
        work_queue.enqueue(work2)
        work_queue.enqueue(work3)

        # Dequeue (should get highest priority first)
        pending = work_queue.dequeue(limit=3)

        assert len(pending) == 3
        assert pending[0].id == "work-002"  # Priority 8
        assert pending[1].id == "work-001"  # Priority 5
        assert pending[2].id == "work-003"  # Priority 3

    def test_priority_filtering(self, work_queue: DistributedWorkQueue) -> None:
        """Test filtering by priority when dequeuing."""
        # Create work items with different priorities
        work1 = QueueWorkItem(id="work-001", task="Task 1", priority=8)
        work2 = QueueWorkItem(id="work-002", task="Task 2", priority=5)
        work3 = QueueWorkItem(id="work-003", task="Task 3", priority=9)

        work_queue.enqueue(work1)
        work_queue.enqueue(work2)
        work_queue.enqueue(work3)

        # Get only high-priority work (>= 8)
        high_priority = work_queue.dequeue(limit=10, priority_filter=8)

        assert len(high_priority) == 2
        assert all(w.priority >= 8 for w in high_priority)

    def test_assign_work_to_node(self, work_queue: DistributedWorkQueue) -> None:
        """Test assigning work to a specific node."""
        # Enqueue work
        work = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work_queue.enqueue(work)

        # Assign to node
        assigned = work_queue.assign("work-001", "node-001")

        assert assigned is not None
        assert assigned.assigned_node == "node-001"
        assert assigned.status == QueueWorkItemStatus.ASSIGNED

    def test_update_work_status(self, work_queue: DistributedWorkQueue) -> None:
        """Test updating work status through lifecycle."""
        # Enqueue and assign work
        work = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work_queue.enqueue(work)
        work_queue.assign("work-001", "node-001")

        # Update to running
        running = work_queue.update_work_status("work-001", QueueWorkItemStatus.RUNNING)
        assert running is not None
        assert running.status == QueueWorkItemStatus.RUNNING
        assert running.started_at is not None

        # Update to completed
        completed = work_queue.update_work_status("work-001", QueueWorkItemStatus.COMPLETED)
        assert completed is not None
        assert completed.status == QueueWorkItemStatus.COMPLETED
        assert completed.completed_at is not None

    def test_work_retry_logic(self, work_queue: DistributedWorkQueue) -> None:
        """Test retrying failed work."""
        # Create work that fails
        work = QueueWorkItem(id="work-001", task="Task 1", priority=5, max_retries=3)
        work_queue.enqueue(work)
        work_queue.assign("work-001", "node-001")

        # Mark as failed
        failed = work_queue.update_work_status(
            "work-001",
            QueueWorkItemStatus.FAILED,
            error="Connection timeout",
        )

        assert failed is not None
        assert failed.status == QueueWorkItemStatus.FAILED
        assert failed.error == "Connection timeout"

        # Retry the work
        retried = work_queue.retry_work("work-001")

        assert retried is not None
        assert retried.status == QueueWorkItemStatus.PENDING
        assert retried.retry_count == 1
        assert retried.assigned_node is None

    def test_max_retries_exceeded(self, work_queue: DistributedWorkQueue) -> None:
        """Test that max retries is enforced."""
        # Create work with max_retries=1
        work = QueueWorkItem(id="work-001", task="Task 1", priority=5, max_retries=1)
        work_queue.enqueue(work)

        # Fail it once
        work_queue.update_work_status("work-001", QueueWorkItemStatus.FAILED)
        work_queue.retry_work("work-001")

        # Fail it again
        work_queue.update_work_status("work-001", QueueWorkItemStatus.FAILED)

        # Should not be able to retry again
        with pytest.raises(ValueError, match="Max retries"):
            work_queue.retry_work("work-001")

    def test_queue_statistics(self, work_queue: DistributedWorkQueue) -> None:
        """Test getting queue statistics."""
        # Add work in different states
        work1 = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work_queue.enqueue(work1)

        work2 = QueueWorkItem(id="work-002", task="Task 2", priority=5)
        work_queue.enqueue(work2)
        work_queue.assign("work-002", "node-001")

        stats = work_queue.get_stats()

        assert stats["pending"] == 1
        assert stats["assigned"] == 1
        assert stats["running"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0


# ============================================================================
# Health Monitoring Tests
# ============================================================================


class TestHealthMonitoring:
    """Tests for health monitoring across nodes."""

    def test_health_config_creation(self) -> None:
        """Test creating health configuration."""
        config = HealthConfig(
            heartbeat_interval=30,
            timeout_threshold=90,
            max_consecutive_failures=3,
        )

        assert config.heartbeat_interval == 30
        assert config.timeout_threshold == 90
        assert config.max_consecutive_failures == 3

    def test_node_health_info(self) -> None:
        """Test node health information model."""
        info = NodeHealthInfo(
            node_id="node-001",
            status=HealthStatus.HEALTHY,
            last_heartbeat=datetime.utcnow(),
            consecutive_failures=0,
        )

        assert info.node_id == "node-001"
        assert info.status == HealthStatus.HEALTHY
        assert info.consecutive_failures == 0

    def test_registry_statistics(self, node_registry: NodeRegistry) -> None:
        """Test getting registry statistics."""
        stats = node_registry.get_stats()

        assert isinstance(stats, RegistryStats)
        assert stats.total_nodes == 4
        assert stats.online_nodes == 3
        assert stats.offline_nodes == 1

    def test_online_percentage(self, node_registry: NodeRegistry) -> None:
        """Test calculating online node percentage."""
        stats = node_registry.get_stats()
        percentage = stats.online_percentage()

        assert percentage == 75.0  # 3 of 4 nodes


# ============================================================================
# Integration Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """End-to-end integration tests for multi-node scenarios."""

    def test_complete_work_distribution_workflow(
        self,
        node_registry: NodeRegistry,
        work_queue: DistributedWorkQueue,
    ) -> None:
        """Test complete workflow from work creation to completion."""
        # Create load balancer
        balancer = LoadBalancer(registry=node_registry)

        # Create work items
        for i in range(5):
            work = QueueWorkItem(
                id=f"work-{i:03d}",
                task=f"Task {i}",
                priority=5 + i,
            )
            work_queue.enqueue(work)

        # Get pending work
        pending = work_queue.dequeue(limit=3)
        assert len(pending) == 3

        # Assign work to nodes using load balancer
        for work in pending:
            node = balancer.select_node()
            assert node is not None

            work_queue.assign(work.id, node.id)
            balancer.record_assignment(node.id, work.id)

        # Verify assignments
        stats = balancer.get_stats()
        assert stats.total_assignments == 3

    def test_node_failure_and_recovery(
        self,
        node_registry: NodeRegistry,
        work_queue: DistributedWorkQueue,
    ) -> None:
        """Test scenario where a node fails and work is reassigned."""
        balancer = LoadBalancer(registry=node_registry)

        # Create and assign work to node-001
        work = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work_queue.enqueue(work)
        work_queue.assign("work-001", "node-001")

        # Simulate node-001 failure
        node_001 = node_registry.lookup("node-001")
        assert node_001 is not None
        node_001.status = NodeStatus.OFFLINE

        # Reassign work to different node
        node_002 = balancer.select_node()
        assert node_002 is not None
        assert node_002.id != "node-001"

        reassigned = work_queue.reassign_work("work-001", node_002.id)
        assert reassigned is not None
        assert reassigned.assigned_node == node_002.id

    def test_priority_based_scheduling(
        self,
        node_registry: NodeRegistry,
        work_queue: DistributedWorkQueue,
    ) -> None:
        """Test that high-priority work is scheduled first."""
        balancer = LoadBalancer(registry=node_registry)

        # Create work with mixed priorities
        for i in range(10):
            priority = 1 if i % 3 == 0 else 5  # Some low priority
            work = QueueWorkItem(
                id=f"work-{i:03d}",
                task=f"Task {i}",
                priority=priority,
            )
            work_queue.enqueue(work)

        # Get high-priority work only
        high_priority = work_queue.dequeue(limit=10, priority_filter=5)

        # Should only get priority >= 5
        assert all(w.priority >= 5 for w in high_priority)

    def test_load_distribution_across_nodes(
        self,
        node_registry: NodeRegistry,
        work_queue: DistributedWorkQueue,
    ) -> None:
        """Test that work is distributed across available nodes."""
        balancer = LoadBalancer(
            registry=node_registry,
            strategy=LoadBalancingStrategy.ROUND_ROBIN,
        )

        # Create multiple work items
        for i in range(9):
            work = QueueWorkItem(
                id=f"work-{i:03d}",
                task=f"Task {i}",
                priority=5,
            )
            work_queue.enqueue(work)

        # Assign all work
        pending = work_queue.dequeue(limit=9)
        assignments = []
        for work in pending:
            node = balancer.select_node()
            assert node is not None

            work_queue.assign(work.id, node.id)
            assignments.append(node.id)

        # Check that work was distributed
        unique_nodes = set(assignments)
        assert len(unique_nodes) > 1  # Should use multiple nodes


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_cluster(self) -> None:
        """Test behavior with empty cluster."""
        cluster = ClusterState(cluster_id="empty-cluster")

        # Should have no nodes
        assert len(cluster.nodes) == 0

        # Health status should be UNHEALTHY
        status = cluster.update_health_status()
        assert status == ClusterStatus.UNHEALTHY

    def test_no_available_nodes(
        self,
        sample_nodes: list[Node],
    ) -> None:
        """Test behavior when no nodes are available."""
        # Create a new registry with all offline nodes
        registry = NodeRegistry()
        for node in sample_nodes:
            offline_node = Node(
                id=node.id,
                address=node.address,
                capabilities=node.capabilities,
                status=NodeStatus.OFFLINE,
                last_seen=node.last_seen,
                metadata=node.metadata,
            )
            registry.register(offline_node)

        balancer = LoadBalancer(registry=registry)

        # Should return None when all nodes are offline
        selected = balancer.select_node()
        assert selected is None

    def test_nonexistent_node_lookup(self, cluster_state: ClusterState) -> None:
        """Test looking up a non-existent node."""
        node = cluster_state.get_node("nonexistent")
        assert node is None

    def test_nonexistent_work_item(self, work_queue: DistributedWorkQueue) -> None:
        """Test retrieving a non-existent work item."""
        work = work_queue.get_work_item("nonexistent")
        assert work is None

    def test_balancer_error_handling(self, node_registry: NodeRegistry) -> None:
        """Test balancer error handling."""
        balancer = LoadBalancer(registry=node_registry)

        # Complete non-existent assignment
        result = balancer.complete_assignment("nonexistent", success=True)
        assert result is False

    def test_duplicate_work_id(self, work_queue: DistributedWorkQueue) -> None:
        """Test handling duplicate work IDs."""
        work1 = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        work2 = QueueWorkItem(id="work-001", task="Task 2", priority=5)

        # Enqueue both with same ID
        work_queue.enqueue(work1)
        work_queue.enqueue(work2)

        # Should only have one
        pending = work_queue.dequeue(limit=10)
        assert len(pending) == 1


# ============================================================================
# Performance and Scalability
# ============================================================================


class TestPerformanceAndScalability:
    """Tests for performance and scalability aspects."""

    def test_large_scale_work_distribution(
        self,
        node_registry: NodeRegistry,
        work_queue: DistributedWorkQueue,
    ) -> None:
        """Test distributing a large number of work items."""
        balancer = LoadBalancer(registry=node_registry)

        # Create many work items
        num_items = 100
        for i in range(num_items):
            work = QueueWorkItem(
                id=f"work-{i:04d}",
                task=f"Task {i}",
                priority=5,
            )
            work_queue.enqueue(work)

        # Get all pending work
        pending = work_queue.dequeue(limit=num_items)
        assert len(pending) == num_items

        # Assign all work
        for work in pending:
            node = balancer.select_node()
            if node:
                work_queue.assign(work.id, node.id)

        # Check stats
        stats = work_queue.get_stats()
        assert stats["pending"] == 0

    def test_concurrent_node_updates(self, cluster_state: ClusterState) -> None:
        """Test handling concurrent updates to nodes."""
        # Simulate rapid updates
        for i in range(10):
            node = cluster_state.get_node("node-001")
            if node:
                node.update_heartbeat()
                cluster_state.touch()

        # Should have updated timestamp
        assert cluster_state.updated_at > cluster_state.created_at

    def test_work_queue_persistence(
        self,
        temp_queue_dir: Path,
    ) -> None:
        """Test that work queue persists across instances."""
        # Create queue and add work
        queue1 = DistributedWorkQueue(queue_dir=temp_queue_dir)
        queue1.initialize()

        work = QueueWorkItem(id="work-001", task="Task 1", priority=5)
        queue1.enqueue(work)

        # Create new queue instance (should load existing data)
        queue2 = DistributedWorkQueue(queue_dir=temp_queue_dir)
        queue2.initialize()

        # Should retrieve the work
        pending = queue2.dequeue(limit=10)
        assert len(pending) == 1
        assert pending[0].id == "work-001"
