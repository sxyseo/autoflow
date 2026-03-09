"""
Unit Tests for Autoflow Node Coordination

Tests the Node and NodeStatus classes for distributed agent coordination.
These tests verify node creation, status tracking, capability management,
and heartbeat functionality.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from autoflow.coordination.node import Node, NodeStatus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_node() -> Node:
    """Create a sample node for testing."""
    return Node(
        id="node-001",
        address="localhost:8080",
        capabilities=["claude-code", "test-runner"],
        status=NodeStatus.ONLINE,
        metadata={"region": "us-west", "cpu": "x64"},
    )


# ============================================================================
# NodeStatus Enum Tests
# ============================================================================


class TestNodeStatus:
    """Tests for NodeStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert NodeStatus.ONLINE.value == "online"
        assert NodeStatus.OFFLINE.value == "offline"
        assert NodeStatus.BUSY.value == "busy"
        assert NodeStatus.DRAINING.value == "draining"
        assert NodeStatus.UNHEALTHY.value == "unhealthy"

    def test_status_is_string_enum(self) -> None:
        """Test that status is a string enum."""
        assert isinstance(NodeStatus.ONLINE, str)


# ============================================================================
# Node Class Tests
# ============================================================================


class TestNodeCreation:
    """Tests for Node creation and initialization."""

    def test_create_node_with_required_fields(self) -> None:
        """Test creating a node with only required fields."""
        node = Node(id="node-001")
        assert node.id == "node-001"
        assert node.address == ""
        assert node.capabilities == []
        assert node.status == NodeStatus.OFFLINE
        assert node.metadata == {}

    def test_create_node_with_all_fields(self, sample_node: Node) -> None:
        """Test creating a node with all fields."""
        assert sample_node.id == "node-001"
        assert sample_node.address == "localhost:8080"
        assert "claude-code" in sample_node.capabilities
        assert "test-runner" in sample_node.capabilities
        assert sample_node.status == NodeStatus.ONLINE
        assert sample_node.metadata["region"] == "us-west"

    def test_last_seen_defaults_to_now(self) -> None:
        """Test that last_seen defaults to current time."""
        before = datetime.utcnow()
        node = Node(id="node-001")
        after = datetime.utcnow()

        assert before <= node.last_seen <= after


class TestNodeHeartbeat:
    """Tests for node heartbeat functionality."""

    def test_update_heartbeat(self, sample_node: Node) -> None:
        """Test updating heartbeat timestamp."""
        old_time = sample_node.last_seen
        # Wait a tiny bit to ensure time difference
        import time
        time.sleep(0.01)

        sample_node.update_heartbeat()

        assert sample_node.last_seen > old_time

    def test_is_online_with_status_online(self, sample_node: Node) -> None:
        """Test is_online returns True when status is ONLINE."""
        assert sample_node.is_online(timeout_seconds=30) is True

    def test_is_online_with_status_offline(self, sample_node: Node) -> None:
        """Test is_online returns False when status is OFFLINE."""
        sample_node.status = NodeStatus.OFFLINE
        assert sample_node.is_online(timeout_seconds=30) is False

    def test_is_online_with_status_busy(self, sample_node: Node) -> None:
        """Test is_online returns False when status is BUSY."""
        sample_node.status = NodeStatus.BUSY
        assert sample_node.is_online(timeout_seconds=30) is False

    def test_is_online_respects_timeout(self, sample_node: Node) -> None:
        """Test is_online respects timeout threshold."""
        # Set last_seen to 60 seconds ago
        sample_node.last_seen = datetime.utcnow() - timedelta(seconds=60)

        # With 30 second timeout, should be offline
        assert sample_node.is_online(timeout_seconds=30) is False

        # With 90 second timeout, should be online
        assert sample_node.is_online(timeout_seconds=90) is True

    def test_is_online_with_recent_heartbeat(self, sample_node: Node) -> None:
        """Test is_online with recent heartbeat."""
        sample_node.update_heartbeat()
        assert sample_node.is_online(timeout_seconds=30) is True


class TestNodeCapabilities:
    """Tests for node capability management."""

    def test_has_capability_true(self, sample_node: Node) -> None:
        """Test has_capability returns True for existing capability."""
        assert sample_node.has_capability("claude-code") is True
        assert sample_node.has_capability("test-runner") is True

    def test_has_capability_false(self, sample_node: Node) -> None:
        """Test has_capability returns False for missing capability."""
        assert sample_node.has_capability("deployer") is False

    def test_add_capability(self, sample_node: Node) -> None:
        """Test adding a new capability."""
        assert sample_node.has_capability("deployer") is False
        sample_node.add_capability("deployer")
        assert sample_node.has_capability("deployer") is True

    def test_add_capability_idempotent(self, sample_node: Node) -> None:
        """Test adding same capability twice is idempotent."""
        initial_count = len(sample_node.capabilities)
        sample_node.add_capability("claude-code")
        assert len(sample_node.capabilities) == initial_count

    def test_remove_capability(self, sample_node: Node) -> None:
        """Test removing a capability."""
        assert sample_node.has_capability("test-runner") is True
        result = sample_node.remove_capability("test-runner")
        assert result is True
        assert sample_node.has_capability("test-runner") is False

    def test_remove_capability_not_found(self, sample_node: Node) -> None:
        """Test removing non-existent capability returns False."""
        result = sample_node.remove_capability("nonexistent")
        assert result is False

    def test_capabilities_list_mutable(self, sample_node: Node) -> None:
        """Test that capabilities list can be modified."""
        initial_count = len(sample_node.capabilities)
        sample_node.capabilities.append("new-capability")
        assert len(sample_node.capabilities) == initial_count + 1


class TestNodeMetadata:
    """Tests for node metadata."""

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """Test metadata defaults to empty dict."""
        node = Node(id="node-001")
        assert node.metadata == {}

    def test_metadata_custom_fields(self, sample_node: Node) -> None:
        """Test custom metadata fields."""
        assert sample_node.metadata["region"] == "us-west"
        assert sample_node.metadata["cpu"] == "x64"

    def test_metadata_mutable(self, sample_node: Node) -> None:
        """Test metadata can be modified."""
        sample_node.metadata["new_field"] = "value"
        assert sample_node.metadata["new_field"] == "value"


class TestNodeStatusTransitions:
    """Tests for node status transitions."""

    def test_status_from_online_to_busy(self, sample_node: Node) -> None:
        """Test transitioning from ONLINE to BUSY."""
        sample_node.status = NodeStatus.BUSY
        assert sample_node.status == NodeStatus.BUSY
        assert sample_node.is_online() is False

    def test_status_from_online_to_draining(self, sample_node: Node) -> None:
        """Test transitioning from ONLINE to DRAINING."""
        sample_node.status = NodeStatus.DRAINING
        assert sample_node.status == NodeStatus.DRAINING

    def test_status_from_online_to_unhealthy(self, sample_node: Node) -> None:
        """Test transitioning from ONLINE to UNHEALTHY."""
        sample_node.status = NodeStatus.UNHEALTHY
        assert sample_node.status == NodeStatus.UNHEALTHY

    def test_status_to_offline(self, sample_node: Node) -> None:
        """Test transitioning to OFFLINE."""
        sample_node.status = NodeStatus.OFFLINE
        assert sample_node.status == NodeStatus.OFFLINE
        assert sample_node.is_online() is False


class TestNodeModel:
    """Tests for Node as a Pydantic model."""

    def test_node_serialization(self, sample_node: Node) -> None:
        """Test node can be serialized to dict."""
        data = sample_node.model_dump()
        assert data["id"] == "node-001"
        assert data["address"] == "localhost:8080"
        assert "claude-code" in data["capabilities"]

    def test_node_deserialization(self) -> None:
        """Test node can be created from dict."""
        data = {
            "id": "node-002",
            "address": "localhost:9000",
            "capabilities": ["deployer"],
            "status": NodeStatus.BUSY,
            "metadata": {"region": "eu-west"},
        }
        node = Node(**data)
        assert node.id == "node-002"
        assert node.address == "localhost:9000"
        assert node.has_capability("deployer")

    def test_node_json_roundtrip(self, sample_node: Node) -> None:
        """Test node can be serialized and deserialized from JSON."""
        import json

        # Serialize
        data = sample_node.model_dump_json()

        # Deserialize
        node_dict = json.loads(data)
        restored = Node(**node_dict)

        assert restored.id == sample_node.id
        assert restored.address == sample_node.address
        assert set(restored.capabilities) == set(sample_node.capabilities)


class TestNodeEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_node_with_empty_capabilities(self) -> None:
        """Test node with empty capabilities list."""
        node = Node(id="node-001", capabilities=[])
        assert node.capabilities == []
        assert node.has_capability("anything") is False

    def test_node_with_special_characters_in_id(self) -> None:
        """Test node ID with special characters."""
        node = Node(id="node-001_special.test")
        assert node.id == "node-001_special.test"

    def test_node_with_unicode_metadata(self) -> None:
        """Test node with unicode characters in metadata."""
        node = Node(
            id="node-001",
            metadata={"description": "节点 🚀", "emoji": "test"},
        )
        assert node.metadata["description"] == "节点 🚀"

    def test_multiple_nodes_independent(self) -> None:
        """Test that multiple node instances are independent."""
        node1 = Node(id="node-001", status=NodeStatus.ONLINE)
        node2 = Node(id="node-002", status=NodeStatus.OFFLINE)

        node1.status = NodeStatus.BUSY

        assert node1.status == NodeStatus.BUSY
        assert node2.status == NodeStatus.OFFLINE
