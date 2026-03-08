"""
Autoflow Coordination Module

Provides distributed agent coordination capabilities for multi-node execution.
Supports node registration, discovery, health monitoring, and work distribution.

This module will be expanded with additional exports in later phases.
"""

# Core data models
from autoflow.coordination.balancer import (
    AssignmentRecord,
    BalancerError,
    LoadBalancer,
    LoadBalancerStats,
    LoadBalancingStrategy,
    create_load_balancer,
)
from autoflow.coordination.cluster import (
    ClusterState,
    ClusterStatus,
    WorkItem,
    WorkItemStatus,
)
from autoflow.coordination.health import (
    HealthCheckError,
    HealthConfig,
    HealthMonitor,
    HealthMonitorStats,
    HealthStatus,
    NodeHealthInfo,
)
from autoflow.coordination.client import NodeClient, NodeClientError
from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry, RegistryStats
from autoflow.coordination.server import NodeServer, create_node_server
from autoflow.coordination.work_queue import (
    DistributedWorkQueue,
    WorkItem as QueueWorkItem,
    WorkItemStatus as QueueWorkItemStatus,
)

__all__ = [
    "Node",
    "NodeStatus",
    "ClusterState",
    "ClusterStatus",
    "WorkItem",
    "WorkItemStatus",
    "NodeRegistry",
    "RegistryStats",
    "NodeClient",
    "NodeClientError",
    "NodeServer",
    "create_node_server",
    "DistributedWorkQueue",
    "QueueWorkItem",
    "QueueWorkItemStatus",
    "LoadBalancer",
    "LoadBalancingStrategy",
    "LoadBalancerStats",
    "AssignmentRecord",
    "BalancerError",
    "create_load_balancer",
    "HealthMonitor",
    "HealthConfig",
    "HealthStatus",
    "NodeHealthInfo",
    "HealthMonitorStats",
    "HealthCheckError",
]
