# Distributed Agent Coordination

<div align="center">

**Multi-Node Execution for Autonomous Development**

Scale autonomous development across multiple machines with proper coordination and state synchronization

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Concepts](#key-concepts)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

Autoflow's distributed coordination system enables agents to run across multiple nodes with proper coordination, state synchronization, and health monitoring. This allows autonomous development workflows to scale beyond single-machine limits.

### Key Capabilities

- **Multi-Node Execution**: Run agents across multiple machines simultaneously
- **Node Discovery**: Automatic node registration and discovery
- **Health Monitoring**: Heartbeat-based health checks with automatic failover
- **Load Balancing**: Intelligent work distribution across available nodes
- **State Synchronization**: Version vector-based state synchronization with conflict resolution
- **Fault Tolerance**: Automatic detection and handling of node failures

### When to Use Distributed Coordination

Use distributed coordination when:

- You need to run more agents than a single machine can handle
- You want to utilize specialized hardware on different machines (GPUs, TPUs)
- You need geographic distribution for latency or redundancy
- You're building large-scale autonomous development systems

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Coordination Layer                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │   Node     │  │  Cluster   │  │   Work     │            │
│  │  Registry  │  │   State    │  │   Queue    │            │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘            │
└────────┼───────────────┼───────────────┼────────────────────┘
         │               │               │
┌────────┼───────────────┼───────────────┼────────────────────┐
│        │       ┌───────┴───────┐       │                    │
│  ┌─────┴─────┐   │   Health    │  ┌────┴─────┐             │
│  │   Load    │   │   Monitor   │  │   State  │             │
│  │ Balancer  │   │             │  │    Sync  │             │
│  └───────────┘   └─────────────┘  └──────────┘             │
└─────────────────────────────────────────────────────────────┘
         │
┌────────┼────────────────────────────────────────────────────┐
│        ▼                                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │   Node     │  │   Node     │  │   Node     │            │
│  │  Server    │  │  Server    │  │  Server    │            │
│  │ (HTTP API) │  │ (HTTP API) │  │ (HTTP API) │            │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘            │
└────────┼───────────────┼───────────────┼───────────────────┘
         │               │               │
    ┌────┴─────┐   ┌─────┴─────┐   ┌────┴─────┐
    │  Agent   │   │  Agent   │   │  Agent   │
    │ Runner   │   │  Runner  │   │  Runner  │
    └──────────┘   └──────────┘   └──────────┘
```

### Communication Protocol

Nodes communicate via HTTP REST API:

- **Node Registration**: `POST /api/v1/nodes/register`
- **Heartbeat**: `POST /api/v1/nodes/{node_id}/heartbeat`
- **Node Discovery**: `GET /api/v1/nodes`
- **Work Assignment**: `POST /api/v1/work/assign`
- **Status Query**: `GET /api/v1/status`
- **Health Check**: `GET /api/v1/ping`

### Data Flow

1. **Node Startup**: Node starts HTTP server and registers with cluster
2. **Work Distribution**: Load balancer assigns work to available nodes
3. **Health Monitoring**: Health monitor tracks node heartbeats
4. **State Sync**: State synchronizer ensures consistency across nodes
5. **Failover**: Unhealthy nodes detected, work reassigned

## Key Concepts

### Nodes

A **Node** represents a participant in the distributed cluster:

```python
from autoflow.coordination.node import Node, NodeStatus

node = Node(
    id="node-001",
    address="localhost:8080",
    capabilities=["claude-code", "test-runner"],
    status=NodeStatus.ONLINE
)
```

**Node Status**:
- `ONLINE`: Node is available for work
- `OFFLINE`: Node is offline
- `BUSY`: Node is at capacity
- `DRAINING`: Node is gracefully shutting down
- `UNHEALTHY`: Node has failed health checks

### Cluster State

**ClusterState** tracks all nodes and work in the cluster:

```python
from autoflow.coordination.cluster import ClusterState, WorkItem

cluster = ClusterState(cluster_id="prod-cluster")
cluster.add_node(node)

work = WorkItem(
    id="work-001",
    task_id="task-001",
    assigned_node="node-001",
    priority=8
)
cluster.add_work_item(work)
```

**Cluster Status**:
- `HEALTHY`: All nodes online
- `DEGRADED`: Some nodes offline
- `UNHEALTHY`: No online nodes
- `REBALANCING`: Work being redistributed

### Health Monitoring

**HealthMonitor** tracks node health via heartbeats:

```python
from autoflow.coordination.health import HealthMonitor, HealthConfig

config = HealthConfig(
    heartbeat_interval=30,
    timeout_threshold=90
)
monitor = HealthMonitor(registry=registry, config=config)
await monitor.start()
```

**Health Status**:
- `HEALTHY`: Node responding normally
- `DEGRADED`: Node slow to respond
- `UNHEALTHY`: Node failed health checks
- `UNKNOWN`: Health status not yet determined

### State Synchronization

**StateSynchronizer** maintains consistency using version vectors:

```python
from autoflow.coordination.sync import StateSynchronizer, VersionVector

sync = StateSynchronizer(node_id="node-001")
sync.update_state("task-001", {"status": "completed"})

# Merge with remote state
remote_version = VersionVector(node_id="node-002", version=5)
snapshot = sync.get_snapshot()
conflicts = sync.merge(remote_version, snapshot)
```

**Conflict Resolution Strategies**:
- `LOCAL_WINS`: Use local version
- `REMOTE_WINS`: Use remote version
- `LATEST_TIMESTAMP`: Use most recent timestamp
- `HIGHEST_VERSION`: Use highest version number
- `MERGE`: Combine both versions
- `MANUAL`: Require manual resolution

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Multiple machines (or localhost for testing)
- Network connectivity between nodes

### Installation

Dependencies are already included in Autoflow's requirements:

```bash
pip install aiohttp  # For HTTP communication
```

### Basic Setup

#### 1. Start the Coordinator Node

```python
from autoflow.coordination.server import create_node_server
from autoflow.coordination.registry import NodeRegistry
import asyncio

async def main():
    # Create registry and server
    registry = NodeRegistry()
    server = create_node_server(
        node_id="coordinator-001",
        host="0.0.0.0",
        port=8080,
        registry=registry
    )

    # Start server
    await server.start()
    print(f"Coordinator running at {server.url}")

    # Keep running
    await asyncio.Event().wait()

asyncio.run(main())
```

#### 2. Start Worker Nodes

On each worker machine:

```python
from autoflow.coordination.server import create_node_server
from autoflow.coordination.client import NodeClient
import asyncio

async def main():
    # Create worker node
    server = create_node_server(
        node_id="worker-001",
        host="0.0.0.0",
        port=8081
    )

    await server.start()

    # Register with coordinator
    client = NodeClient(base_url="http://coordinator:8080")
    await client.register_node(
        node_id="worker-001",
        address="worker-001:8081",
        capabilities=["claude-code", "test-runner"]
    )

    print(f"Worker registered and ready")

    # Start heartbeat loop
    while True:
        await asyncio.sleep(30)
        await client.send_heartbeat("worker-001")

asyncio.run(main())
```

#### 3. Distribute Work

```python
from autoflow.coordination.balancer import LoadBalancer
from autoflow.coordination.client import NodeClient

async def distribute_work():
    # Get available nodes
    client = NodeClient(base_url="http://coordinator:8080")
    nodes = await client.list_nodes()

    # Create load balancer
    balancer = LoadBalancer()

    # Assign work to least loaded node
    node = balancer.select_node(nodes, capability="claude-code")
    if node:
        await client.assign_work(
            work_id="work-001",
            task={"type": "implementation", "spec": "my-spec"},
            assigned_node=node.id
        )

asyncio.run(distribute_work())
```

## Configuration

### Node Configuration

Each node can be configured with:

```python
from autoflow.coordination.server import create_node_server

server = create_node_server(
    node_id="worker-001",
    host="0.0.0.0",
    port=8081,
    registry=None  # Creates new registry if None
)
```

### Health Monitoring Configuration

```python
from autoflow.coordination.health import HealthConfig

config = HealthConfig(
    heartbeat_interval=30,      # Seconds between heartbeats
    timeout_threshold=90,       # Seconds before node marked unhealthy
    degraded_threshold=60,      # Seconds before node marked degraded
    check_timeout=5,            # Timeout for individual health checks
    max_consecutive_failures=3, # Failures before marking unhealthy
    enable_auto_recovery=True,  # Allow nodes to recover after failures
    recovery_threshold=2        # Successes needed to recover
)
```

### Load Balancing Configuration

```python
from autoflow.coordination.balancer import LoadBalancingStrategy

# Use specific strategy
balancer = LoadBalancer(strategy=LoadBalancingStrategy.LEAST_LOADED)

# Available strategies:
# - ROUND_ROBIN: Distribute work evenly
# - LEAST_LOADED: Send work to node with least active work
# - CAPABILITY_BASED: Consider node capabilities
# - RANDOM: Random selection
```

## Usage

### Node Registration

```python
from autoflow.coordination.client import NodeClient

client = NodeClient(base_url="http://coordinator:8080")

# Register node with cluster
await client.register_node(
    node_id="worker-001",
    address="worker-001:8081",
    capabilities=["claude-code", "test-runner"],
    metadata={"region": "us-west", "gpu": True}
)
```

### Node Discovery

```python
# List all nodes
nodes = await client.list_nodes()

# Get specific node
node = await client.get_node("worker-001")

# Filter by capability
capable_nodes = [n for n in nodes if "claude-code" in n.capabilities]
```

### Work Assignment

```python
# Assign work to specific node
await client.assign_work(
    work_id="work-001",
    task={
        "type": "implementation",
        "spec": "my-spec",
        "task_id": "task-001"
    },
    assigned_node="worker-001",
    priority=8,
    metadata={"deadline": "2025-03-10"}
)

# Get work status
status = await client.get_work_status("work-001")
```

### Health Monitoring

```python
from autoflow.coordination.health import HealthMonitor

# Start health monitor
monitor = HealthMonitor(registry=registry, config=config)
await monitor.start()

# Check specific node
health = await monitor.check_health("worker-001")
print(f"Node health: {health.status}")

# Get cluster health
stats = await monitor.get_cluster_stats()
print(f"Healthy nodes: {stats.healthy_count}/{stats.total_count}")

# Stop monitor
await monitor.stop()
```

### State Synchronization

```python
from autoflow.coordination.sync import StateSynchronizer

# Create synchronizer
sync = StateSynchronizer(node_id="node-001")

# Update local state
sync.update_state("task-001", {"status": "completed", "result": "success"})

# Get snapshot for sharing
snapshot = sync.get_snapshot()

# Merge remote state
conflicts = sync.merge(
    remote_version=VersionVector(node_id="node-002", version=5),
    remote_snapshot=remote_snapshot,
    resolution=ConflictResolution.LATEST_TIMESTAMP
)

if conflicts:
    print(f"Found {len(conflicts)} conflicts")
```

## API Reference

### Node API

#### `Node`

Represents a node in the cluster.

**Methods**:
- `update_heartbeat()`: Update last_seen timestamp
- `is_online(timeout_seconds=30)`: Check if node is online
- `has_capability(capability)`: Check if node has capability
- `add_capability(capability)`: Add a capability
- `remove_capability(capability)`: Remove a capability

#### `NodeRegistry`

Manages node registration and discovery.

**Methods**:
- `register(node)`: Register a node
- `lookup(node_id)`: Look up node by ID
- `unregister(node_id)`: Remove node from registry
- `list_nodes()`: Get all nodes
- `get_online_nodes(timeout_seconds=30)`: Get online nodes
- `get_nodes_by_capability(capability)`: Get nodes with capability
- `update_heartbeat(node_id)`: Update node heartbeat
- `get_stats()`: Get registry statistics

### Cluster API

#### `ClusterState`

Manages cluster-level state.

**Methods**:
- `add_node(node)`: Add node to cluster
- `remove_node(node_id)`: Remove node from cluster
- `get_node(node_id)`: Get node by ID
- `get_online_nodes(timeout_seconds=30)`: Get online nodes
- `add_work_item(work)`: Add work item
- `get_work_for_node(node_id)`: Get work for specific node
- `get_pending_work()`: Get pending work items
- `update_health_status(timeout_seconds=30)`: Update cluster health
- `find_least_loaded_node(capability=None)`: Find least loaded node

#### `WorkItem`

Represents a unit of work.

**Methods**:
- `start()`: Mark work as started
- `complete(status=WorkItemStatus.COMPLETED)`: Mark work as completed
- `duration_seconds()`: Calculate work duration

### Health Monitoring API

#### `HealthMonitor`

Monitors node health.

**Methods**:
- `start()`: Start health monitoring
- `stop()`: Stop health monitoring
- `check_health(node_id)`: Check health of specific node
- `get_cluster_stats()`: Get cluster health statistics
- `get_unhealthy_nodes()`: Get list of unhealthy nodes
- `mark_healthy(node_id)`: Mark node as healthy
- `mark_unhealthy(node_id)`: Mark node as unhealthy

### State Synchronization API

#### `StateSynchronizer`

Manages state synchronization.

**Methods**:
- `update_state(key, value)`: Update local state
- `get_state(key)`: Get local state value
- `get_snapshot()`: Get state snapshot
- `merge(remote_version, remote_snapshot, resolution)`: Merge remote state
- `get_version()`: Get current version vector

#### `VersionVector`

Tracks version information.

**Methods**:
- `increment()`: Increment version
- `compare(other)`: Compare with another version vector
- `is_descendant(other)`: Check if this version is descendant of other

## Best Practices

### 1. Node Registration

- Register nodes with clear, descriptive IDs
- Include all capabilities when registering
- Set appropriate metadata (region, hardware, etc.)
- Handle registration failures gracefully

### 2. Health Monitoring

- Use appropriate heartbeat intervals (30-60 seconds)
- Set timeout thresholds based on network conditions
- Enable auto-recovery for transient failures
- Monitor health statistics regularly

### 3. Load Balancing

- Choose strategy based on workload characteristics
- Consider node capabilities when assigning work
- Monitor node utilization
- Handle node failures gracefully

### 4. State Synchronization

- Use appropriate conflict resolution strategy
- Sync state before critical operations
- Handle merge conflicts appropriately
- Keep state snapshots small and focused

### 5. Error Handling

- Always handle connection errors
- Implement retry logic with backoff
- Log failures for debugging
- Provide graceful degradation

## Troubleshooting

### Nodes Not Discovering Each Other

```bash
# Check if nodes are registered
curl http://coordinator:8080/api/v1/nodes

# Check node status
curl http://coordinator:8080/api/v1/status

# Verify network connectivity
ping worker-001
telnet worker-001 8081
```

### Health Checks Failing

```python
# Check health configuration
config = HealthConfig(
    heartbeat_interval=30,
    timeout_threshold=90
)

# Increase timeout if network is slow
config.timeout_threshold = 120

# Check if nodes are sending heartbeats
stats = await monitor.get_cluster_stats()
print(f"Last heartbeat: {stats.last_heartbeat}")
```

### Work Not Being Distributed

```python
# Check if nodes are online
online_nodes = cluster.get_online_nodes()
print(f"Online nodes: {len(online_nodes)}")

# Check if nodes have required capabilities
capable_nodes = registry.get_nodes_by_capability("claude-code")
print(f"Capable nodes: {len(capable_nodes)}")

# Check work queue status
pending_work = cluster.get_pending_work()
print(f"Pending work: {len(pending_work)}")
```

### State Synchronization Conflicts

```python
# Check for conflicts
conflicts = sync.merge(remote_version, remote_snapshot)

if conflicts:
    print(f"Found {len(conflicts)} conflicts:")
    for conflict in conflicts:
        print(f"  - {conflict.key}: {conflict.resolution}")

# Use manual resolution for critical conflicts
resolution = ConflictResolution.MANUAL
conflicts = sync.merge(remote_version, remote_snapshot, resolution)
```

### Performance Issues

```python
# Adjust load balancing strategy
balancer = LoadBalancer(strategy=LoadBalancingStrategy.LEAST_LOADED)

# Increase health check intervals
config = HealthConfig(heartbeat_interval=60)

# Batch work assignments
for work_batch in chunked_work_items:
    await assign_work_batch(work_batch)
```

---

<div align="center">

**[⬆ Back to Top](#distributed-agent-coordination)**

For more information, see the main [README](../README.md)

</div>
