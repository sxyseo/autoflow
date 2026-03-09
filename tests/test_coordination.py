"""
Unit Tests for Autoflow Node Registry

Tests the NodeRegistry and RegistryStats classes for managing distributed nodes.
These tests verify node registration, lookup, filtering, and statistics.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry, RegistryStats


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_nodes() -> list[Node]:
    """Create sample nodes for testing."""
    return [
        Node(
            id="node-001",
            address="localhost:8080",
            capabilities=["claude-code", "test-runner"],
            status=NodeStatus.ONLINE,
        ),
        Node(
            id="node-002",
            address="localhost:8081",
            capabilities=["claude-code", "deployer"],
            status=NodeStatus.BUSY,
        ),
        Node(
            id="node-003",
            address="localhost:8082",
            capabilities=["test-runner"],
            status=NodeStatus.ONLINE,
        ),
        Node(
            id="node-004",
            address="localhost:8083",
            capabilities=["deployer"],
            status=NodeStatus.OFFLINE,
        ),
        Node(
            id="node-005",
            address="localhost:8084",
            capabilities=["claude-code"],
            status=NodeStatus.UNHEALTHY,
        ),
    ]


@pytest.fixture
def empty_registry() -> NodeRegistry:
    """Create an empty registry."""
    return NodeRegistry()


@pytest.fixture
def populated_registry(sample_nodes: list[Node]) -> NodeRegistry:
    """Create a registry populated with sample nodes."""
    registry = NodeRegistry()
    for node in sample_nodes:
        registry.register(node)
    return registry


# ============================================================================
# RegistryStats Tests
# ============================================================================


class TestRegistryStats:
    """Tests for RegistryStats class."""

    def test_create_stats(self) -> None:
        """Test creating stats with default values."""
        stats = RegistryStats()
        assert stats.total_nodes == 0
        assert stats.online_nodes == 0
        assert stats.offline_nodes == 0

    def test_create_stats_with_values(self) -> None:
        """Test creating stats with specific values."""
        stats = RegistryStats(
            total_nodes=10,
            online_nodes=8,
            offline_nodes=1,
            busy_nodes=1,
            unhealthy_nodes=0,
        )
        assert stats.total_nodes == 10
        assert stats.online_nodes == 8

    def test_online_percentage(self) -> None:
        """Test calculating online percentage."""
        stats = RegistryStats(total_nodes=10, online_nodes=8)
        assert stats.online_percentage() == 80.0

    def test_online_percentage_zero_total(self) -> None:
        """Test online percentage with zero total."""
        stats = RegistryStats(total_nodes=0, online_nodes=0)
        assert stats.online_percentage() == 0.0

    def test_healthy_percentage(self) -> None:
        """Test calculating healthy percentage."""
        stats = RegistryStats(total_nodes=10, unhealthy_nodes=2)
        assert stats.healthy_percentage() == 80.0

    def test_healthy_percentage_zero_total(self) -> None:
        """Test healthy percentage with zero total."""
        stats = RegistryStats(total_nodes=0, unhealthy_nodes=0)
        assert stats.healthy_percentage() == 0.0

    def test_last_updated_defaults(self) -> None:
        """Test last_updated defaults to now."""
        before = datetime.utcnow()
        stats = RegistryStats()
        after = datetime.utcnow()
        assert before <= stats.last_updated <= after


# ============================================================================
# NodeRegistry Creation Tests
# ============================================================================


class TestNodeRegistryCreation:
    """Tests for NodeRegistry initialization."""

    def test_create_in_memory_registry(self) -> None:
        """Test creating an in-memory registry."""
        registry = NodeRegistry()
        assert registry.get_node_count() == 0

    def test_create_persistent_registry(self, tmp_path: Path) -> None:
        """Test creating a persistent registry."""
        persist_path = tmp_path / "registry.json"
        registry = NodeRegistry(persist_path=persist_path)
        assert registry.get_node_count() == 0

    def test_load_from_disk_missing_file(self, tmp_path: Path) -> None:
        """Test loading from disk when file doesn't exist."""
        persist_path = tmp_path / "nonexistent.json"
        registry = NodeRegistry(persist_path=persist_path)
        assert registry.get_node_count() == 0


# ============================================================================
# Node Registration Tests
# ============================================================================


class TestNodeRegistration:
    """Tests for node registration."""

    def test_register_single_node(self, empty_registry: NodeRegistry) -> None:
        """Test registering a single node."""
        node = Node(id="node-001", address="localhost:8080")
        empty_registry.register(node)
        assert empty_registry.get_node_count() == 1

    def test_register_multiple_nodes(self, empty_registry: NodeRegistry) -> None:
        """Test registering multiple nodes."""
        for i in range(3):
            node = Node(id=f"node-{i:03d}", address=f"localhost:{8080 + i}")
            empty_registry.register(node)
        assert empty_registry.get_node_count() == 3

    def test_register_update_existing_node(
        self, empty_registry: NodeRegistry
    ) -> None:
        """Test that registering same node ID updates it."""
        node1 = Node(
            id="node-001",
            address="localhost:8080",
            capabilities=["claude-code"],
        )
        node2 = Node(
            id="node-001",
            address="localhost:8081",  # Different address
            capabilities=["claude-code", "deployer"],  # Additional capability
        )

        empty_registry.register(node1)
        empty_registry.register(node2)

        assert empty_registry.get_node_count() == 1
        retrieved = empty_registry.lookup("node-001")
        assert retrieved is not None
        assert retrieved.address == "localhost:8081"
        assert "deployer" in retrieved.capabilities


# ============================================================================
# Node Lookup Tests
# ============================================================================


class TestNodeLookup:
    """Tests for node lookup."""

    def test_lookup_existing_node(self, populated_registry: NodeRegistry) -> None:
        """Test looking up an existing node."""
        node = populated_registry.lookup("node-001")
        assert node is not None
        assert node.id == "node-001"
        assert node.address == "localhost:8080"

    def test_lookup_nonexistent_node(self, populated_registry: NodeRegistry) -> None:
        """Test looking up a non-existent node."""
        node = populated_registry.lookup("nonexistent")
        assert node is None

    def test_lookup_after_unregistration(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test looking up a node after unregistering it."""
        populated_registry.unregister("node-001")
        node = populated_registry.lookup("node-001")
        assert node is None


# ============================================================================
# Node Unregistration Tests
# ============================================================================


class TestNodeUnregistration:
    """Tests for node unregistration."""

    def test_unregister_existing_node(self, populated_registry: NodeRegistry) -> None:
        """Test unregistering an existing node."""
        initial_count = populated_registry.get_node_count()
        result = populated_registry.unregister("node-001")
        assert result is True
        assert populated_registry.get_node_count() == initial_count - 1

    def test_unregister_nonexistent_node(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test unregistering a non-existent node."""
        initial_count = populated_registry.get_node_count()
        result = populated_registry.unregister("nonexistent")
        assert result is False
        assert populated_registry.get_node_count() == initial_count

    def test_unregister_all_nodes(self, populated_registry: NodeRegistry) -> None:
        """Test unregistering all nodes."""
        populated_registry.clear()
        assert populated_registry.get_node_count() == 0


# ============================================================================
# Node Listing Tests
# ============================================================================


class TestNodeListing:
    """Tests for node listing and filtering."""

    def test_list_all_nodes(self, populated_registry: NodeRegistry) -> None:
        """Test listing all nodes."""
        nodes = populated_registry.list_nodes()
        assert len(nodes) == 5

    def test_list_nodes_by_status_online(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test listing only online nodes."""
        nodes = populated_registry.list_nodes(status=NodeStatus.ONLINE)
        assert len(nodes) == 2
        assert all(n.status == NodeStatus.ONLINE for n in nodes)

    def test_list_nodes_by_status_busy(self, populated_registry: NodeRegistry) -> None:
        """Test listing only busy nodes."""
        nodes = populated_registry.list_nodes(status=NodeStatus.BUSY)
        assert len(nodes) == 1
        assert nodes[0].id == "node-002"

    def test_list_nodes_by_capability(self, populated_registry: NodeRegistry) -> None:
        """Test listing nodes by capability."""
        nodes = populated_registry.list_nodes(capability="claude-code")
        assert len(nodes) == 3
        assert all(n.has_capability("claude-code") for n in nodes)

    def test_list_nodes_by_status_and_capability(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test listing nodes with both filters."""
        nodes = populated_registry.list_nodes(
            status=NodeStatus.ONLINE, capability="test-runner"
        )
        # Both node-001 and node-003 have test-runner and are ONLINE
        assert len(nodes) == 2
        node_ids = {n.id for n in nodes}
        assert node_ids == {"node-001", "node-003"}


# ============================================================================
# Online Nodes Tests
# ============================================================================


class TestOnlineNodes:
    """Tests for getting online nodes."""

    def test_get_online_nodes(self, populated_registry: NodeRegistry) -> None:
        """Test getting online nodes."""
        online = populated_registry.get_online_nodes()
        # Only ONLINE status nodes are returned
        assert len(online) == 2

    def test_get_online_nodes_with_timeout(
        self, sample_nodes: list[Node]
    ) -> None:
        """Test online nodes with timeout."""
        registry = NodeRegistry()

        # Create a node with old heartbeat
        old_node = Node(id="old-node", status=NodeStatus.ONLINE)
        old_node.last_seen = datetime.utcnow() - __import__(
            "datetime"
        ).timedelta(seconds=60)
        registry.register(old_node)

        # Create a node with recent heartbeat
        new_node = Node(id="new-node", status=NodeStatus.ONLINE)
        registry.register(new_node)

        # With 30 second timeout, only new_node should be online
        online = registry.get_online_nodes(timeout_seconds=30)
        assert len(online) == 1
        assert online[0].id == "new-node"


# ============================================================================
# Available Nodes Tests
# ============================================================================


class TestAvailableNodes:
    """Tests for getting available nodes."""

    def test_get_available_nodes(self, populated_registry: NodeRegistry) -> None:
        """Test getting available nodes (online and not busy)."""
        available = populated_registry.get_available_nodes()
        # ONLINE nodes that aren't BUSY
        assert len(available) == 2

    def test_get_available_nodes_with_capability(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test getting available nodes with specific capability."""
        available = populated_registry.get_available_nodes(
            capability="claude-code"
        )
        # Only node-001 has claude-code and is ONLINE
        assert len(available) == 1
        assert available[0].id == "node-001"


# ============================================================================
# Capability Filtering Tests
# ============================================================================


class TestCapabilityFiltering:
    """Tests for capability-based filtering."""

    def test_get_nodes_by_capability_claude_code(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test getting nodes with claude-code capability."""
        nodes = populated_registry.get_nodes_by_capability("claude-code")
        assert len(nodes) == 3
        node_ids = {n.id for n in nodes}
        assert node_ids == {"node-001", "node-002", "node-005"}

    def test_get_nodes_by_capability_test_runner(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test getting nodes with test-runner capability."""
        nodes = populated_registry.get_nodes_by_capability("test-runner")
        assert len(nodes) == 2
        node_ids = {n.id for n in nodes}
        assert node_ids == {"node-001", "node-003"}

    def test_get_nodes_by_nonexistent_capability(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test getting nodes with non-existent capability."""
        nodes = populated_registry.get_nodes_by_capability("nonexistent")
        assert len(nodes) == 0


# ============================================================================
# Status Update Tests
# ============================================================================


class TestStatusUpdate:
    """Tests for status updates."""

    def test_update_node_status(self, populated_registry: NodeRegistry) -> None:
        """Test updating node status."""
        result = populated_registry.update_node_status("node-001", NodeStatus.BUSY)
        assert result is True

        node = populated_registry.lookup("node-001")
        assert node is not None
        assert node.status == NodeStatus.BUSY

    def test_update_node_status_nonexistent(
        self, populated_registry: NodeRegistry
    ) -> None:
        """Test updating status of non-existent node."""
        result = populated_registry.update_node_status(
            "nonexistent", NodeStatus.BUSY
        )
        assert result is False

    def test_update_heartbeat(self, populated_registry: NodeRegistry) -> None:
        """Test updating node heartbeat."""
        node = populated_registry.lookup("node-001")
        assert node is not None
        old_last_seen = node.last_seen

        import time
        time.sleep(0.01)

        result = populated_registry.update_heartbeat("node-001")
        assert result is True

        node = populated_registry.lookup("node-001")
        assert node is not None
        assert node.last_seen > old_last_seen


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Tests for registry statistics."""

    def test_get_stats(self, populated_registry: NodeRegistry) -> None:
        """Test getting registry statistics."""
        stats = populated_registry.get_stats()
        assert stats.total_nodes == 5
        assert stats.online_nodes == 2
        assert stats.offline_nodes == 1
        assert stats.busy_nodes == 1
        assert stats.unhealthy_nodes == 1


# ============================================================================
# Persistence Tests
# ============================================================================


class TestPersistence:
    """Tests for registry persistence."""

    def test_save_to_disk(self, tmp_path: Path) -> None:
        """Test saving registry to disk."""
        persist_path = tmp_path / "registry.json"
        registry = NodeRegistry(persist_path=persist_path)

        node = Node(id="node-001", address="localhost:8080")
        registry.register(node)

        assert persist_path.exists()

    def test_load_from_disk(self, tmp_path: Path) -> None:
        """Test loading registry from disk."""
        persist_path = tmp_path / "registry.json"

        # Create and save registry
        registry1 = NodeRegistry(persist_path=persist_path)
        node = Node(id="node-001", address="localhost:8080")
        registry1.register(node)

        # Load into new registry
        registry2 = NodeRegistry(persist_path=persist_path)
        assert registry2.get_node_count() == 1

        loaded_node = registry2.lookup("node-001")
        assert loaded_node is not None
        assert loaded_node.id == "node-001"
        assert loaded_node.address == "localhost:8080"

    def test_persistence_preserves_capabilities(self, tmp_path: Path) -> None:
        """Test that persistence preserves node capabilities."""
        persist_path = tmp_path / "registry.json"

        registry1 = NodeRegistry(persist_path=persist_path)
        node = Node(
            id="node-001",
            address="localhost:8080",
            capabilities=["claude-code", "test-runner"],
        )
        registry1.register(node)

        registry2 = NodeRegistry(persist_path=persist_path)
        loaded = registry2.lookup("node-001")
        assert loaded is not None
        assert "claude-code" in loaded.capabilities
        assert "test-runner" in loaded.capabilities


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_clear_empty_registry(self, empty_registry: NodeRegistry) -> None:
        """Test clearing an empty registry."""
        empty_registry.clear()
        assert empty_registry.get_node_count() == 0

    def test_register_node_with_same_id_multiple_times(
        self, empty_registry: NodeRegistry
    ) -> None:
        """Test registering node with same ID multiple times."""
        node = Node(id="node-001", address="localhost:8080")
        empty_registry.register(node)
        empty_registry.register(node)
        empty_registry.register(node)

        assert empty_registry.get_node_count() == 1

    def test_get_node_count_empty(self, empty_registry: NodeRegistry) -> None:
        """Test getting node count for empty registry."""
        assert empty_registry.get_node_count() == 0

    def test_unregister_from_empty_registry(
        self, empty_registry: NodeRegistry
    ) -> None:
        """Test unregistering from empty registry."""
        result = empty_registry.unregister("node-001")
        assert result is False
