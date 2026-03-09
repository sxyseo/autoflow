"""
Unit Tests for Autoflow State Synchronization

Tests the StateSynchronizer, VersionVector, StateSnapshot, and StateConflict classes
for distributed state synchronization with conflict resolution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.coordination.sync import (
    ConflictResolution,
    StateConflict,
    StateSnapshot,
    StateSynchronizer,
    SyncStatus,
    VersionVector,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_version_vector() -> VersionVector:
    """Create a sample version vector."""
    return VersionVector(
        node_id="node-001",
        version=1,
        metadata={"author": "test"},
    )


@pytest.fixture
def state_sync() -> StateSynchronizer:
    """Create a state synchronizer."""
    return StateSynchronizer(node_id="node-001")


# ============================================================================
# ConflictResolution Enum Tests
# ============================================================================


class TestConflictResolution:
    """Tests for ConflictResolution enum."""

    def test_resolution_strategies(self) -> None:
        """Test all resolution strategies exist."""
        assert ConflictResolution.LOCAL_WINS.value == "local_wins"
        assert ConflictResolution.REMOTE_WINS.value == "remote_wins"
        assert ConflictResolution.LATEST_TIMESTAMP.value == "latest_timestamp"
        assert ConflictResolution.HIGHEST_VERSION.value == "highest_version"
        assert ConflictResolution.MERGE.value == "merge"
        assert ConflictResolution.MANUAL.value == "manual"


# ============================================================================
# SyncStatus Enum Tests
# ============================================================================


class TestSyncStatus:
    """Tests for SyncStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert SyncStatus.SYNCED.value == "synced"
        assert SyncStatus.OUT_OF_SYNC.value == "out_of_sync"
        assert SyncStatus.CONFLICT.value == "conflict"
        assert SyncStatus.SYNCING.value == "syncing"
        assert SyncStatus.ERROR.value == "error"


# ============================================================================
# VersionVector Tests
# ============================================================================


class TestVersionVector:
    """Tests for VersionVector."""

    def test_create_version_vector(self, sample_version_vector: VersionVector) -> None:
        """Test creating a version vector."""
        assert sample_version_vector.node_id == "node-001"
        assert sample_version_vector.version == 1
        assert sample_version_vector.metadata["author"] == "test"

    def test_increment_version(self, sample_version_vector: VersionVector) -> None:
        """Test incrementing version."""
        old_version = sample_version_vector.version
        sample_version_vector.increment()
        assert sample_version_vector.version == old_version + 1

    def test_increment_updates_timestamp(
        self, sample_version_vector: VersionVector
    ) -> None:
        """Test that increment updates timestamp."""
        old_timestamp = sample_version_vector.timestamp
        import time
        time.sleep(0.01)

        sample_version_vector.increment()
        assert sample_version_vector.timestamp > old_timestamp

    def test_dominates_true(self) -> None:
        """Test dominates returns True for higher version."""
        vv1 = VersionVector(node_id="node-001", version=2)
        vv2 = VersionVector(node_id="node-001", version=1)
        assert vv1.dominates(vv2) is True

    def test_dominates_false_same_version(self) -> None:
        """Test dominates returns False for same version."""
        vv1 = VersionVector(node_id="node-001", version=1)
        vv2 = VersionVector(node_id="node-001", version=1)
        assert vv1.dominates(vv2) is False

    def test_dominates_false_different_node(self) -> None:
        """Test dominates returns False for different nodes."""
        vv1 = VersionVector(node_id="node-001", version=2)
        vv2 = VersionVector(node_id="node-002", version=1)
        assert vv1.dominates(vv2) is False

    def test_is_concurrent_true(self) -> None:
        """Test is_concurrent returns True for different nodes."""
        vv1 = VersionVector(node_id="node-001", version=1)
        vv2 = VersionVector(node_id="node-002", version=1)
        assert vv1.is_concurrent(vv2) is True

    def test_is_concurrent_false_same_node(self) -> None:
        """Test is_concurrent returns False for same node."""
        vv1 = VersionVector(node_id="node-001", version=1)
        vv2 = VersionVector(node_id="node-001", version=2)
        assert vv1.is_concurrent(vv2) is False

    def test_to_dict(self, sample_version_vector: VersionVector) -> None:
        """Test converting version vector to dict."""
        data = sample_version_vector.to_dict()
        assert data["node_id"] == "node-001"
        assert data["version"] == 1
        assert "timestamp" in data

    def test_from_dict(self) -> None:
        """Test creating version vector from dict."""
        data = {
            "node_id": "node-002",
            "version": 5,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {"key": "value"},
        }
        vv = VersionVector.from_dict(data)
        assert vv.node_id == "node-002"
        assert vv.version == 5


# ============================================================================
# StateSnapshot Tests
# ============================================================================


class TestStateSnapshot:
    """Tests for StateSnapshot."""

    def test_create_snapshot(self) -> None:
        """Test creating a state snapshot."""
        snapshot = StateSnapshot(
            node_id="node-001",
            state={"key": "value"},
        )
        assert snapshot.node_id == "node-001"
        assert snapshot.state["key"] == "value"

    def test_get_version(self) -> None:
        """Test getting version from snapshot."""
        vv = VersionVector(node_id="node-001", version=1)
        snapshot = StateSnapshot(
            node_id="node-001",
            version_vectors={"task-001": vv.to_dict()},
            state={"task-001": {"status": "pending"}},
        )

        retrieved_vv = snapshot.get_version("task-001")
        assert retrieved_vv is not None
        assert retrieved_vv.version == 1

    def test_get_state(self) -> None:
        """Test getting state from snapshot."""
        snapshot = StateSnapshot(
            node_id="node-001",
            state={"key": "value"},
        )
        assert snapshot.get_state("key") == "value"
        assert snapshot.get_state("nonexistent", default="default") == "default"

    def test_to_dict(self) -> None:
        """Test converting snapshot to dict."""
        snapshot = StateSnapshot(node_id="node-001")
        data = snapshot.to_dict()
        assert data["node_id"] == "node-001"
        assert "version_vectors" in data
        assert "state" in data

    def test_from_dict(self) -> None:
        """Test creating snapshot from dict."""
        data = {
            "node_id": "node-002",
            "version_vectors": {},
            "state": {"key": "value"},
            "created_at": datetime.utcnow().isoformat(),
            "checksum": None,
            "metadata": {},
        }
        snapshot = StateSnapshot.from_dict(data)
        assert snapshot.node_id == "node-002"
        assert snapshot.state["key"] == "value"


# ============================================================================
# StateConflict Tests
# ============================================================================


class TestStateConflict:
    """Tests for StateConflict."""

    @pytest.fixture
    def sample_conflict(self) -> StateConflict:
        """Create a sample conflict."""
        return StateConflict(
            key="task-001",
            local_value={"status": "pending"},
            remote_value={"status": "completed"},
            local_version=VersionVector(node_id="node-001", version=1),
            remote_version=VersionVector(node_id="node-002", version=2),
        )

    def test_resolve_local_wins(self, sample_conflict: StateConflict) -> None:
        """Test resolving conflict with local wins."""
        result = sample_conflict.resolve(ConflictResolution.LOCAL_WINS)
        assert result == {"status": "pending"}
        assert sample_conflict.resolution == ConflictResolution.LOCAL_WINS

    def test_resolve_remote_wins(self, sample_conflict: StateConflict) -> None:
        """Test resolving conflict with remote wins."""
        result = sample_conflict.resolve(ConflictResolution.REMOTE_WINS)
        assert result == {"status": "completed"}
        assert sample_conflict.resolution == ConflictResolution.REMOTE_WINS

    def test_resolve_highest_version(self, sample_conflict: StateConflict) -> None:
        """Test resolving conflict with highest version."""
        result = sample_conflict.resolve(ConflictResolution.HIGHEST_VERSION)
        # Remote version is higher (2 vs 1)
        assert result == {"status": "completed"}

    def test_resolve_latest_timestamp(self, sample_conflict: StateConflict) -> None:
        """Test resolving conflict with latest timestamp."""
        # Set remote timestamp to be newer
        sample_conflict.remote_version.timestamp = (
            sample_conflict.local_version.timestamp + timedelta(seconds=10)
        )
        result = sample_conflict.resolve(ConflictResolution.LATEST_TIMESTAMP)
        assert result == {"status": "completed"}

    def test_resolve_merge_dicts(self) -> None:
        """Test resolving conflict by merging dicts."""
        conflict = StateConflict(
            key="task-001",
            local_value={"status": "pending", "assignee": "alice"},
            remote_value={"status": "completed", "priority": "high"},
            local_version=VersionVector(node_id="node-001", version=1),
            remote_version=VersionVector(node_id="node-002", version=1),
        )

        result = conflict.resolve(ConflictResolution.MERGE)
        # Should merge both dicts
        assert "assignee" in result
        assert "priority" in result

    def test_resolve_merge_non_dicts(self) -> None:
        """Test merging non-dict values defaults to local."""
        conflict = StateConflict(
            key="task-001",
            local_value="string_value",
            remote_value="another_string",
            local_version=VersionVector(node_id="node-001", version=1),
            remote_version=VersionVector(node_id="node-002", version=1),
        )

        result = conflict.resolve(ConflictResolution.MERGE)
        assert result == "string_value"

    def test_resolve_manual_raises_error(self, sample_conflict: StateConflict) -> None:
        """Test that manual resolution raises error."""
        with pytest.raises(ValueError, match="Manual resolution required"):
            sample_conflict.resolve(ConflictResolution.MANUAL)


# ============================================================================
# StateSynchronizer Tests
# ============================================================================


class TestStateSynchronizer:
    """Tests for StateSynchronizer."""

    def test_create_synchronizer(self, state_sync: StateSynchronizer) -> None:
        """Test creating a state synchronizer."""
        assert state_sync.node_id == "node-001"
        assert state_sync.state == {}
        assert state_sync.sync_status == SyncStatus.SYNCED

    def test_update_state(self, state_sync: StateSynchronizer) -> None:
        """Test updating state."""
        vv = state_sync.update_state("task-001", {"status": "pending"})
        assert vv.version == 1
        assert state_sync.state["task-001"] == {"status": "pending"}

    def test_update_state_increments_version(
        self, state_sync: StateSynchronizer
    ) -> None:
        """Test that updating state increments version."""
        state_sync.update_state("task-001", {"status": "pending"})
        state_sync.update_state("task-001", {"status": "running"})

        vv = state_sync.get_version("task-001")
        assert vv is not None
        assert vv.version == 2

    def test_get_state(self, state_sync: StateSynchronizer) -> None:
        """Test getting state value."""
        state_sync.update_state("task-001", {"status": "pending"})
        value = state_sync.get_state("task-001")
        assert value == {"status": "pending"}

    def test_get_state_default(self, state_sync: StateSynchronizer) -> None:
        """Test getting state with default value."""
        value = state_sync.get_state("nonexistent", default="default")
        assert value == "default"

    def test_delete_state(self, state_sync: StateSynchronizer) -> None:
        """Test deleting state."""
        state_sync.update_state("task-001", {"status": "pending"})
        result = state_sync.delete_state("task-001")
        assert result is True
        assert state_sync.get_state("task-001") is None

    def test_delete_nonexistent_state(self, state_sync: StateSynchronizer) -> None:
        """Test deleting non-existent state."""
        result = state_sync.delete_state("nonexistent")
        assert result is False

    def test_get_snapshot(self, state_sync: StateSynchronizer) -> None:
        """Test getting state snapshot."""
        state_sync.update_state("task-001", {"status": "pending"})
        snapshot = state_sync.get_snapshot()
        assert snapshot.node_id == "node-001"
        assert snapshot.state["task-001"] == {"status": "pending"}

    def test_merge_new_key(self, state_sync: StateSynchronizer) -> None:
        """Test merging snapshot with new key."""
        remote_snapshot = StateSnapshot(
            node_id="node-002",
            version_vectors={
                "task-002": VersionVector(
                    node_id="node-002", version=1
                ).to_dict()
            },
            state={"task-002": {"status": "completed"}},
        )

        conflicts = state_sync.merge(remote_snapshot)
        assert len(conflicts) == 0
        assert state_sync.state["task-002"] == {"status": "completed"}

    def test_merge_with_conflict(self, state_sync: StateSynchronizer) -> None:
        """Test merging snapshot with conflict."""
        # Add local state
        state_sync.update_state("task-001", {"status": "pending"})

        # Create remote snapshot with different value
        remote_snapshot = StateSnapshot(
            node_id="node-002",
            version_vectors={
                "task-001": VersionVector(
                    node_id="node-002", version=1
                ).to_dict()
            },
            state={"task-001": {"status": "completed"}},
        )

        conflicts = state_sync.merge(remote_snapshot)
        assert len(conflicts) == 1
        assert conflicts[0].key == "task-001"

    def test_merge_dominant_version(self, state_sync: StateSynchronizer) -> None:
        """Test merging with dominant remote version."""
        # Add local state
        state_sync.update_state("task-001", {"status": "pending"})

        # Create remote snapshot with higher version from same node
        remote_snapshot = StateSnapshot(
            node_id="node-001",  # Same node
            version_vectors={
                "task-001": VersionVector(
                    node_id="node-001", version=2  # Higher version
                ).to_dict()
            },
            state={"task-001": {"status": "completed"}},
        )

        conflicts = state_sync.merge(remote_snapshot)
        # No conflict - remote dominates
        assert len(conflicts) == 0
        assert state_sync.state["task-001"] == {"status": "completed"}

    def test_get_conflicts(self, state_sync: StateSynchronizer) -> None:
        """Test getting unresolved conflicts."""
        # Create a conflict
        local_vv = VersionVector(node_id="node-001", version=1)
        remote_vv = VersionVector(node_id="node-002", version=1)
        conflict = StateConflict(
            key="task-001",
            local_value={"status": "pending"},
            remote_value={"status": "completed"},
            local_version=local_vv,
            remote_version=remote_vv,
            resolution=None,  # Unresolved
        )
        state_sync._conflicts.append(conflict)

        conflicts = state_sync.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].resolution is None

    def test_resolve_conflict(self, state_sync: StateSynchronizer) -> None:
        """Test manually resolving a conflict."""
        # Create an unresolved conflict
        local_vv = VersionVector(node_id="node-001", version=1)
        remote_vv = VersionVector(node_id="node-002", version=1)
        conflict = StateConflict(
            key="task-001",
            local_value={"status": "pending"},
            remote_value={"status": "completed"},
            local_version=local_vv,
            remote_version=remote_vv,
            resolution=None,
        )
        state_sync._conflicts.append(conflict)

        result = state_sync.resolve_conflict("task-001", {"status": "in_progress"})
        assert result is True
        assert state_sync.state["task-001"] == {"status": "in_progress"}

    def test_get_sync_status(self, state_sync: StateSynchronizer) -> None:
        """Test getting sync status."""
        status = state_sync.get_sync_status()
        assert status == SyncStatus.SYNCED

    def test_clear(self, state_sync: StateSynchronizer) -> None:
        """Test clearing state."""
        state_sync.update_state("task-001", {"status": "pending"})
        state_sync.clear()
        assert len(state_sync.state) == 0
        assert len(state_sync.version_vectors) == 0


# ============================================================================
# StateSynchronizer Persistence Tests
# ============================================================================


class TestStateSynchronizerPersistence:
    """Tests for StateSynchronizer persistence."""

    def test_save_to_disk(self, state_sync: StateSynchronizer, tmp_path: Path) -> None:
        """Test saving state to disk."""
        state_sync.state_dir = tmp_path / "sync"
        state_sync.update_state("task-001", {"status": "pending"})

        path = state_sync.save_to_disk()
        assert path.exists()

    def test_load_from_disk(self, state_sync: StateSynchronizer, tmp_path: Path) -> None:
        """Test loading state from disk."""
        state_sync.state_dir = tmp_path / "sync"
        state_sync.update_state("task-001", {"status": "pending"})
        state_sync.save_to_disk()

        # Create new synchronizer and load
        new_sync = StateSynchronizer(node_id="node-001", state_dir=tmp_path / "sync")
        result = new_sync.load_from_disk()
        assert result is True
        assert new_sync.state["task-001"] == {"status": "pending"}

    def test_load_from_disk_no_file(self, state_sync: StateSynchronizer, tmp_path: Path) -> None:
        """Test loading from disk when file doesn't exist."""
        state_sync.state_dir = tmp_path / "sync"
        result = state_sync.load_from_disk()
        assert result is False


# ============================================================================
# StateSynchronizer AntiEntropy Tests
# ============================================================================


class TestStateSynchronizerAntiEntropy:
    """Tests for anti-entropy reconciliation."""

    def test_anti_entropy_no_remotes(self, state_sync: StateSynchronizer) -> None:
        """Test anti-entropy with no remote nodes."""
        result = state_sync.anti_entropy(lambda: [])
        assert result["success"] is True
        assert result["nodes_synced"] == 0

    def test_anti_entropy_with_remotes(self, state_sync: StateSynchronizer) -> None:
        """Test anti-entropy with remote snapshots."""
        # Add local state
        state_sync.update_state("task-001", {"status": "pending"})

        # Create remote snapshot
        remote_snapshot = StateSnapshot(
            node_id="node-002",
            version_vectors={
                "task-002": VersionVector(
                    node_id="node-002", version=1
                ).to_dict()
            },
            state={"task-002": {"status": "completed"}},
        )

        result = state_sync.anti_entropy(lambda: [remote_snapshot])
        assert result["success"] is True
        assert result["nodes_synced"] == 1
        assert result["keys_updated"] > 0

    def test_anti_entropy_full_sync(self, state_sync: StateSynchronizer) -> None:
        """Test anti-entropy with full sync."""
        state_sync.update_state("task-001", {"status": "pending"})

        remote_snapshot = StateSnapshot(
            node_id="node-002",
            version_vectors={},
            state={},
        )

        result = state_sync.anti_entropy(
            lambda: [remote_snapshot],
            full_sync=True,
        )
        assert result["success"] is True

    def test_anti_entropy_invalid_return_type(
        self, state_sync: StateSynchronizer
    ) -> None:
        """Test anti-entropy with invalid return type."""
        result = state_sync.anti_entropy(lambda: "invalid")
        assert result["success"] is False
        assert "error" in result


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_version_vector_zero_version(self) -> None:
        """Test version vector with zero version."""
        vv = VersionVector(node_id="node-001", version=0)
        assert vv.version == 0

    def test_state_snapshot_empty(self) -> None:
        """Test state snapshot with empty state."""
        snapshot = StateSnapshot(node_id="node-001")
        assert len(snapshot.state) == 0
        assert len(snapshot.version_vectors) == 0

    def test_state_sync_update_with_metadata(self, state_sync: StateSynchronizer) -> None:
        """Test updating state with metadata."""
        vv = state_sync.update_state(
            "task-001",
            {"status": "pending"},
            metadata={"author": "alice"},
        )
        assert "author" in vv.metadata

    def test_merge_empty_snapshot(self, state_sync: StateSynchronizer) -> None:
        """Test merging empty snapshot."""
        snapshot = StateSnapshot(node_id="node-002")
        conflicts = state_sync.merge(snapshot)
        assert len(conflicts) == 0

    def test_get_version_nonexistent(self, state_sync: StateSynchronizer) -> None:
        """Test getting version for nonexistent key."""
        vv = state_sync.get_version("nonexistent")
        assert vv is None
