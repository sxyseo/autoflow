"""
Autoflow Coordination Module

Provides distributed agent coordination capabilities for multi-node execution.
Supports node registration, discovery, health monitoring, and work distribution.

This module will be expanded with additional exports in later phases.
"""

# Core data models
from autoflow.coordination.cluster import (
    ClusterState,
    ClusterStatus,
    WorkItem,
    WorkItemStatus,
)
from autoflow.coordination.node import Node, NodeStatus

__all__ = [
    "Node",
    "NodeStatus",
    "ClusterState",
    "ClusterStatus",
    "WorkItem",
    "WorkItemStatus",
]
