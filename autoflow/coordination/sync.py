"""
Autoflow State Synchronization Module

Provides distributed state synchronization with version vectors and conflict
resolution for maintaining consistency across nodes in a cluster.

Usage:
    from autoflow.coordination.sync import StateSynchronizer, VersionVector

    # Create a synchronizer
    sync = StateSynchronizer(node_id="node-001")

    # Track state changes
    sync.update_state("task-001", {"status": "completed"})

    # Synchronize with another node
    remote_version = VersionVector(node_id="node-002", version=5)
    snapshot = sync.get_snapshot()
    conflicts = sync.merge(remote_version, snapshot)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ConflictResolution(str, Enum):
    """Strategy for resolving state conflicts."""

    # Use local version (our state wins)
    LOCAL_WINS = "local_wins"

    # Use remote version (their state wins)
    REMOTE_WINS = "remote_wins"

    # Use most recent timestamp
    LATEST_TIMESTAMP = "latest_timestamp"

    # Use highest version number
    HIGHEST_VERSION = "highest_version"

    # Merge both versions (combine fields)
    MERGE = "merge"

    # Manual resolution required
    MANUAL = "manual"


class SyncStatus(str, Enum):
    """Status of synchronization operations."""

    SYNCED = "synced"
    OUT_OF_SYNC = "out_of_sync"
    CONFLICT = "conflict"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class VersionVector:
    """
    Tracks version information for state across nodes.

    A version vector is a distributed systems tool for tracking causal
    relationships between updates across different nodes. Each node
    maintains its own version counter, which increments on each update.

    Attributes:
        node_id: ID of the node this version vector represents
        version: Version counter for this node
        timestamp: When this version was created
        metadata: Additional version information

    Example:
        >>> vv = VersionVector(node_id="node-001", version=1)
        >>> vv.increment()
        >>> print(vv.version)  # 2
    """

    node_id: str
    version: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def increment(self) -> None:
        """
        Increment the version counter.

        Updates the version number and refreshes the timestamp.

        Example:
            >>> vv = VersionVector(node_id="node-001", version=1)
            >>> vv.increment()
            >>> print(vv.version)  # 2
        """
        self.version += 1
        self.timestamp = datetime.utcnow()

    def dominates(self, other: VersionVector) -> bool:
        """
        Check if this version vector dominates another.

        A version vector dominates another if its version is strictly
        greater and the node_id is the same.

        Args:
            other: Other version vector to compare

        Returns:
            True if this version dominates the other

        Example:
            >>> vv1 = VersionVector(node_id="node-001", version=2)
            >>> vv2 = VersionVector(node_id="node-001", version=1)
            >>> print(vv1.dominates(vv2))  # True
        """
        if self.node_id != other.node_id:
            return False
        return self.version > other.version

    def is_concurrent(self, other: VersionVector) -> bool:
        """
        Check if this version vector is concurrent with another.

        Two versions are concurrent if they're from different nodes
        (no causal relationship).

        Args:
            other: Other version vector to compare

        Returns:
            True if versions are concurrent

        Example:
            >>> vv1 = VersionVector(node_id="node-001", version=1)
            >>> vv2 = VersionVector(node_id="node-002", version=1)
            >>> print(vv1.is_concurrent(vv2))  # True
        """
        return self.node_id != other.node_id

    def to_dict(self) -> dict[str, Any]:
        """
        Convert version vector to dictionary.

        Returns:
            Dictionary representation of version vector

        Example:
            >>> vv = VersionVector(node_id="node-001", version=1)
            >>> d = vv.to_dict()
            >>> print(d["node_id"])  # "node-001"
        """
        return {
            "node_id": self.node_id,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionVector:
        """
        Create version vector from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            VersionVector instance

        Example:
            >>> data = {"node_id": "node-001", "version": 1,
            ...         "timestamp": "2026-03-08T00:00:00",
            ...         "metadata": {}}
            >>> vv = VersionVector.from_dict(data)
        """
        return cls(
            node_id=data["node_id"],
            version=data.get("version", 0),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            metadata=data.get("metadata", {}),
        )


class StateConflict(BaseModel):
    """
    Represents a conflict between two state versions.

    Attributes:
        key: State key that has a conflict
        local_value: Local state value
        remote_value: Remote state value
        local_version: Local version vector
        remote_version: Remote version vector
        resolution: How the conflict was resolved (None if unresolved)
        resolved_value: Final value after resolution (None if unresolved)
        detected_at: When the conflict was detected

    Example:
        >>> conflict = StateConflict(
        ...     key="task-001",
        ...     local_value={"status": "pending"},
        ...     remote_value={"status": "completed"},
        ...     local_version=VersionVector(node_id="node-001", version=1),
        ...     remote_version=VersionVector(node_id="node-002", version=2)
        ... )
    """

    key: str
    local_value: Any
    remote_value: Any
    local_version: VersionVector
    remote_version: VersionVector
    resolution: Optional[ConflictResolution] = None
    resolved_value: Optional[Any] = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    def resolve(
        self,
        strategy: ConflictResolution,
    ) -> Any:
        """
        Resolve the conflict using the specified strategy.

        Args:
            strategy: Conflict resolution strategy to apply

        Returns:
            Resolved value

        Raises:
            ValueError: If strategy is MANUAL (requires manual resolution)

        Example:
            >>> conflict.resolve(ConflictResolution.LATEST_TIMESTAMP)
        """
        self.resolution = strategy

        if strategy == ConflictResolution.LOCAL_WINS:
            self.resolved_value = self.local_value
        elif strategy == ConflictResolution.REMOTE_WINS:
            self.resolved_value = self.remote_value
        elif strategy == ConflictResolution.HIGHEST_VERSION:
            # Compare versions - higher wins
            if self.local_version.version >= self.remote_version.version:
                self.resolved_value = self.local_value
            else:
                self.resolved_value = self.remote_value
        elif strategy == ConflictResolution.LATEST_TIMESTAMP:
            # Compare timestamps - more recent wins
            if self.local_version.timestamp >= self.remote_version.timestamp:
                self.resolved_value = self.local_value
            else:
                self.resolved_value = self.remote_value
        elif strategy == ConflictResolution.MERGE:
            # Attempt to merge dictionaries
            if isinstance(self.local_value, dict) and isinstance(self.remote_value, dict):
                merged = {**self.local_value, **self.remote_value}
                self.resolved_value = merged
            else:
                # Can't merge non-dict values, default to local
                self.resolved_value = self.local_value
        elif strategy == ConflictResolution.MANUAL:
            raise ValueError("Manual resolution required - cannot auto-resolve")

        return self.resolved_value


class StateSnapshot(BaseModel):
    """
    Represents a snapshot of state at a point in time.

    Captures the complete state of a node at a specific moment,
    including all key-value pairs and version information.

    Attributes:
        node_id: ID of the node that created this snapshot
        version_vectors: Dictionary of version vectors per key
        state: Dictionary of state key-value pairs
        created_at: When the snapshot was created
        checksum: Optional checksum for integrity verification
        metadata: Additional snapshot information

    Example:
        >>> snapshot = StateSnapshot(
        ...     node_id="node-001",
        ...     version_vectors={"task-001": VersionVector(node_id="node-001", version=1)},
        ...     state={"task-001": {"status": "pending"}}
        ... )
    """

    node_id: str
    version_vectors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    checksum: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_version(self, key: str) -> Optional[VersionVector]:
        """
        Get version vector for a specific key.

        Args:
            key: State key

        Returns:
            VersionVector if found, None otherwise

        Example:
            >>> vv = snapshot.get_version("task-001")
        """
        if key in self.version_vectors:
            return VersionVector.from_dict(self.version_vectors[key])
        return None

    def get_state(self, key: str, default: Any = None) -> Any:
        """
        Get state value for a specific key.

        Args:
            key: State key
            default: Default value if key not found

        Returns:
            State value or default

        Example:
            >>> value = snapshot.get_state("task-001", default={})
        """
        return self.state.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert snapshot to dictionary.

        Returns:
            Dictionary representation

        Example:
            >>> data = snapshot.to_dict()
        """
        return {
            "node_id": self.node_id,
            "version_vectors": self.version_vectors,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateSnapshot:
        """
        Create snapshot from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            StateSnapshot instance

        Example:
            >>> snapshot = StateSnapshot.from_dict(data)
        """
        return cls(
            node_id=data["node_id"],
            version_vectors=data.get("version_vectors", {}),
            state=data.get("state", {}),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.utcnow().isoformat())
            ),
            checksum=data.get("checksum"),
            metadata=data.get("metadata", {}),
        )


class StateSynchronizer:
    """
    Manages state synchronization across distributed nodes.

    The StateSynchronizer tracks state changes with version vectors,
    detects conflicts when merging state from other nodes, and provides
    strategies for automatic or manual conflict resolution.

    Attributes:
        node_id: ID of this node
        state_dir: Directory for persistent state storage
        state: Current state dictionary
        version_vectors: Version vectors for each state key
        sync_status: Current synchronization status

    Example:
        >>> sync = StateSynchronizer(node_id="node-001")
        >>> sync.update_state("task-001", {"status": "completed"})
        >>> snapshot = sync.get_snapshot()
        >>> conflicts = sync.merge(snapshot.version_vectors, snapshot.state)
    """

    def __init__(
        self,
        node_id: str,
        state_dir: Union[str, Path] = ".autoflow/sync",
    ):
        """
        Initialize the StateSynchronizer.

        Args:
            node_id: Unique identifier for this node
            state_dir: Directory for persistent state storage

        Example:
            >>> sync = StateSynchronizer(node_id="node-001")
        """
        self.node_id = node_id
        self.state_dir = Path(state_dir)
        self.state: dict[str, Any] = {}
        self.version_vectors: dict[str, VersionVector] = {}
        self.sync_status = SyncStatus.SYNCED
        self._conflicts: list[StateConflict] = []

    def update_state(
        self,
        key: str,
        value: Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> VersionVector:
        """
        Update a state key and increment its version.

        Args:
            key: State key to update
            value: New value for the key
            metadata: Optional metadata to attach to version

        Returns:
            Updated version vector

        Example:
            >>> sync = StateSynchronizer(node_id="node-001")
            >>> vv = sync.update_state("task-001", {"status": "completed"})
        """
        # Get or create version vector
        if key in self.version_vectors:
            vv = self.version_vectors[key]
            vv.increment()
        else:
            vv = VersionVector(node_id=self.node_id, version=1)

        if metadata:
            vv.metadata.update(metadata)

        # Update state
        self.state[key] = value
        self.version_vectors[key] = vv

        return vv

    def get_state(
        self,
        key: str,
        default: Any = None,
    ) -> Optional[Any]:
        """
        Get a state value by key.

        Args:
            key: State key
            default: Default value if key not found

        Returns:
            State value or default

        Example:
            >>> value = sync.get_state("task-001", default={})
        """
        return self.state.get(key, default)

    def delete_state(
        self,
        key: str,
    ) -> bool:
        """
        Delete a state key.

        Args:
            key: State key to delete

        Returns:
            True if key was deleted, False if not found

        Example:
            >>> if sync.delete_state("task-001"):
            ...     print("Deleted")
        """
        if key in self.state:
            del self.state[key]
            if key in self.version_vectors:
                del self.version_vectors[key]
            return True
        return False

    def get_snapshot(self) -> StateSnapshot:
        """
        Create a snapshot of current state.

        Returns:
            StateSnapshot with current state and versions

        Example:
            >>> snapshot = sync.get_snapshot()
        """
        version_dicts = {
            key: vv.to_dict() for key, vv in self.version_vectors.items()
        }

        return StateSnapshot(
            node_id=self.node_id,
            version_vectors=version_dicts,
            state=self.state.copy(),
        )

    def merge(
        self,
        remote_snapshot: StateSnapshot,
        resolution_strategy: ConflictResolution = ConflictResolution.HIGHEST_VERSION,
    ) -> list[StateConflict]:
        """
        Merge remote snapshot into local state.

        Detects conflicts between local and remote state, and resolves
        them using the specified strategy.

        Args:
            remote_snapshot: Remote state snapshot to merge
            resolution_strategy: Strategy for resolving conflicts

        Returns:
            List of conflicts that were detected and resolved

        Example:
            >>> remote_snapshot = sync.get_snapshot()
            >>> conflicts = sync.merge(remote_snapshot)
        """
        conflicts: list[StateConflict] = []

        # Process each key in remote snapshot
        for key, remote_value in remote_snapshot.state.items():
            remote_vv_dict = remote_snapshot.version_vectors.get(key)
            if not remote_vv_dict:
                continue

            remote_vv = VersionVector.from_dict(remote_vv_dict)

            # Check if key exists locally
            if key not in self.state:
                # No conflict - new key from remote
                self.state[key] = remote_value
                self.version_vectors[key] = remote_vv
                continue

            # Key exists - check version for conflicts
            local_vv = self.version_vectors.get(key)
            if not local_vv:
                # No local version info - accept remote
                self.state[key] = remote_value
                self.version_vectors[key] = remote_vv
                continue

            # Check for concurrent updates (conflict)
            if local_vv.is_concurrent(remote_vv):
                # Concurrent updates from different nodes
                conflict = StateConflict(
                    key=key,
                    local_value=self.state[key],
                    remote_value=remote_value,
                    local_version=local_vv,
                    remote_version=remote_vv,
                )

                # Resolve conflict
                try:
                    resolved_value = conflict.resolve(resolution_strategy)
                    self.state[key] = resolved_value

                    # Update version to max of both
                    if remote_vv.version > local_vv.version:
                        self.version_vectors[key] = remote_vv
                    else:
                        local_vv.increment()

                    conflicts.append(conflict)
                except ValueError:
                    # Manual resolution required
                    conflicts.append(conflict)
                    self.sync_status = SyncStatus.CONFLICT
                    continue

            elif remote_vv.dominates(local_vv):
                # Remote version is newer - accept it
                self.state[key] = remote_value
                self.version_vectors[key] = remote_vv
            # else: local version is newer - keep it

        if conflicts:
            self._conflicts.extend(conflicts)

        return conflicts

    def get_conflicts(self) -> list[StateConflict]:
        """
        Get list of unresolved conflicts.

        Returns:
            List of conflicts requiring manual resolution

        Example:
            >>> conflicts = sync.get_conflicts()
            >>> for conflict in conflicts:
            ...     print(f"Conflict: {conflict.key}")
        """
        return [c for c in self._conflicts if c.resolution is None]

    def resolve_conflict(
        self,
        key: str,
        value: Any,
    ) -> bool:
        """
        Manually resolve a conflict for a specific key.

        Args:
            key: State key with conflict
            value: Resolved value to apply

        Returns:
            True if conflict was resolved, False if key not found in conflicts

        Example:
            >>> sync.resolve_conflict("task-001", {"status": "completed"})
        """
        for conflict in self._conflicts:
            if conflict.key == key and conflict.resolution is None:
                conflict.resolved_value = value
                conflict.resolution = ConflictResolution.MANUAL
                self.state[key] = value
                self.sync_status = SyncStatus.SYNCED
                return True
        return False

    def get_version(self, key: str) -> Optional[VersionVector]:
        """
        Get version vector for a specific key.

        Args:
            key: State key

        Returns:
            VersionVector if found, None otherwise

        Example:
            >>> vv = sync.get_version("task-001")
            >>> if vv:
            ...     print(f"Version: {vv.version}")
        """
        return self.version_vectors.get(key)

    def get_sync_status(self) -> SyncStatus:
        """
        Get current synchronization status.

        Returns:
            Current sync status

        Example:
            >>> status = sync.get_sync_status()
            >>> print(f"Status: {status}")
        """
        # Check if we have unresolved conflicts
        if self.get_conflicts():
            self.sync_status = SyncStatus.CONFLICT
        return self.sync_status

    def save_to_disk(self) -> Path:
        """
        Save current state to disk for persistence.

        Returns:
            Path to saved state file

        Example:
            >>> path = sync.save_to_disk()
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)

        snapshot = self.get_snapshot()
        file_path = self.state_dir / f"{self.node_id}-state.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False)

        return file_path

    def load_from_disk(self) -> bool:
        """
        Load state from disk.

        Returns:
            True if state was loaded, False if file not found

        Example:
            >>> if sync.load_from_disk():
            ...     print("State loaded")
        """
        file_path = self.state_dir / f"{self.node_id}-state.json"

        if not file_path.exists():
            return False

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        snapshot = StateSnapshot.from_dict(data)

        # Restore state
        self.state = snapshot.state
        self.version_vectors = {
            key: VersionVector.from_dict(vv_dict)
            for key, vv_dict in snapshot.version_vectors.items()
        }

        return True

    def clear(self) -> None:
        """
        Clear all state and version vectors.

        Example:
            >>> sync.clear()
        """
        self.state.clear()
        self.version_vectors.clear()
        self._conflicts.clear()
        self.sync_status = SyncStatus.SYNCED

    def anti_entropy(
        self,
        remote_state_func: callable,
        resolution_strategy: ConflictResolution = ConflictResolution.HIGHEST_VERSION,
        full_sync: bool = False,
    ) -> dict[str, Any]:
        """
        Perform anti-entropy reconciliation with remote nodes.

        Anti-entropy is a protocol used in distributed systems to periodically
        reconcile state between nodes to ensure eventual consistency. This method
        exchanges state information with remote nodes, detects inconsistencies,
        and merges differences using configurable strategies.

        The process:
        1. Fetch remote state snapshots from other nodes
        2. Compare version vectors to detect divergences
        3. Merge remote state into local state
        4. Detect and resolve conflicts
        5. Return summary of synchronization results

        Args:
            remote_state_func: Callable that returns list of remote StateSnapshot objects
            resolution_strategy: Strategy for resolving conflicts during merge
            full_sync: If True, perform full state comparison. If False, only
                      compare keys with divergent version vectors.

        Returns:
            Dictionary with reconciliation results including:
            - success: Whether reconciliation completed successfully
            - nodes_synced: Number of nodes synchronized with
            - keys_updated: Number of state keys updated
            - conflicts_detected: Number of conflicts found
            - conflicts_resolved: Number of conflicts automatically resolved
            - conflicts_manual: Number of conflicts requiring manual resolution
            - sync_duration_seconds: Time taken for synchronization
            - timestamp: When reconciliation was performed

        Raises:
            ValueError: If remote_state_func returns invalid data
            Exception: If reconciliation fails

        Example:
            >>> def fetch_remote_snapshots():
            ...     # Fetch state from other nodes in cluster
            ...     return [node1_snapshot, node2_snapshot]
            >>>
            >>> result = sync.anti_entropy(
            ...     fetch_remote_snapshots,
            ...     resolution_strategy=ConflictResolution.LATEST_TIMESTAMP
            ... )
            >>> print(f"Synced with {result['nodes_synced']} nodes")
            >>> print(f"Updated {result['keys_updated']} keys")
        """
        from datetime import timedelta

        start_time = datetime.utcnow()

        result: dict[str, Any] = {
            "success": False,
            "nodes_synced": 0,
            "keys_updated": 0,
            "conflicts_detected": 0,
            "conflicts_resolved": 0,
            "conflicts_manual": 0,
            "sync_duration_seconds": 0.0,
            "timestamp": start_time.isoformat(),
            "error": None,
        }

        try:
            # Fetch remote state snapshots
            remote_snapshots = remote_state_func()

            if not isinstance(remote_snapshots, list):
                raise ValueError(
                    "remote_state_func must return a list of StateSnapshot objects"
                )

            if not remote_snapshots:
                result["success"] = True
                result["error"] = "No remote nodes to synchronize with"
                result["sync_duration_seconds"] = (
                    datetime.utcnow() - start_time
                ).total_seconds()
                return result

            # Process each remote snapshot
            total_conflicts: list[StateConflict] = []
            keys_to_sync: set[str] = set()

            for remote_snapshot in remote_snapshots:
                # Validate snapshot
                if not isinstance(remote_snapshot, StateSnapshot):
                    continue

                # Skip if snapshot is from this node
                if remote_snapshot.node_id == self.node_id:
                    continue

                result["nodes_synced"] += 1

                # Determine which keys need synchronization
                if full_sync:
                    # Full sync: compare all keys
                    remote_keys = set(remote_snapshot.state.keys())
                    local_keys = set(self.state.keys())
                    keys_to_sync.update(remote_keys | local_keys)
                else:
                    # Incremental sync: only keys with divergent versions
                    for key, remote_vv_dict in remote_snapshot.version_vectors.items():
                        if key not in self.version_vectors:
                            # New key from remote
                            keys_to_sync.add(key)
                        else:
                            local_vv = self.version_vectors[key]
                            remote_vv = VersionVector.from_dict(remote_vv_dict)

                            # Check if versions are concurrent (divergent)
                            if local_vv.is_concurrent(remote_vv):
                                keys_to_sync.add(key)
                            elif remote_vv.dominates(local_vv):
                                keys_to_sync.add(key)

            # If no keys need sync, return early
            if not keys_to_sync and not full_sync:
                result["success"] = True
                result["sync_duration_seconds"] = (
                    datetime.utcnow() - start_time
                ).total_seconds()
                return result

            # Perform merge for each remote snapshot
            for remote_snapshot in remote_snapshots:
                if not isinstance(remote_snapshot, StateSnapshot):
                    continue
                if remote_snapshot.node_id == self.node_id:
                    continue

                try:
                    conflicts = self.merge(remote_snapshot, resolution_strategy)
                    total_conflicts.extend(conflicts)
                except Exception as e:
                    # Continue with other nodes even if one fails
                    result["error"] = f"Merge failed with node {remote_snapshot.node_id}: {e}"
                    continue

            # Count results
            result["keys_updated"] = len(keys_to_sync)
            result["conflicts_detected"] = len(total_conflicts)

            # Categorize conflicts
            for conflict in total_conflicts:
                if conflict.resolution == ConflictResolution.MANUAL:
                    result["conflicts_manual"] += 1
                else:
                    result["conflicts_resolved"] += 1

            # Update sync status
            if result["conflicts_manual"] > 0:
                self.sync_status = SyncStatus.CONFLICT
            elif total_conflicts:
                self.sync_status = SyncStatus.SYNCED
            else:
                self.sync_status = SyncStatus.SYNCED

            result["success"] = True

        except Exception as e:
            result["error"] = f"Anti-entropy reconciliation failed: {e}"
            self.sync_status = SyncStatus.ERROR
        finally:
            result["sync_duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
            result["timestamp"] = datetime.utcnow().isoformat()

        return result
