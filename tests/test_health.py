"""
Unit Tests for Autoflow Health Monitoring

Tests the HealthMonitor, HealthConfig, and NodeHealthInfo classes for monitoring
distributed node health through heartbeats.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.coordination.health import (
    HealthCheckError,
    HealthConfig,
    HealthMonitor,
    HealthMonitorStats,
    HealthStatus,
    NodeHealthInfo,
)
from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_config() -> HealthConfig:
    """Create a sample health config."""
    return HealthConfig(
        heartbeat_interval=30,
        timeout_threshold=90,
        degraded_threshold=60,
        check_timeout=5,
        max_consecutive_failures=3,
        enable_auto_recovery=True,
        recovery_threshold=2,
    )


@pytest.fixture
def sample_registry() -> NodeRegistry:
    """Create a sample node registry."""
    registry = NodeRegistry()
    registry.register(
        Node(
            id="node-001",
            address="localhost:8080",
            status=NodeStatus.ONLINE,
        )
    )
    registry.register(
        Node(
            id="node-002",
            address="localhost:8081",
            status=NodeStatus.BUSY,
        )
    )
    return registry


@pytest.fixture
def health_monitor(sample_registry: NodeRegistry, sample_config: HealthConfig) -> HealthMonitor:
    """Create a health monitor."""
    return HealthMonitor(registry=sample_registry, config=sample_config)


# ============================================================================
# HealthStatus Enum Tests
# ============================================================================


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


# ============================================================================
# HealthConfig Tests
# ============================================================================


class TestHealthConfig:
    """Tests for HealthConfig dataclass."""

    def test_default_config(self) -> None:
        """Test creating config with defaults."""
        config = HealthConfig()
        assert config.heartbeat_interval == 30
        assert config.timeout_threshold == 90
        assert config.degraded_threshold == 60
        assert config.check_timeout == 5
        assert config.max_consecutive_failures == 3
        assert config.enable_auto_recovery is True
        assert config.recovery_threshold == 2

    def test_custom_config(self) -> None:
        """Test creating config with custom values."""
        config = HealthConfig(
            heartbeat_interval=60,
            timeout_threshold=120,
            degraded_threshold=90,
        )
        assert config.heartbeat_interval == 60
        assert config.timeout_threshold == 120


# ============================================================================
# NodeHealthInfo Tests
# ============================================================================


class TestNodeHealthInfo:
    """Tests for NodeHealthInfo."""

    def test_create_health_info(self) -> None:
        """Test creating health info."""
        info = NodeHealthInfo(node_id="node-001")
        assert info.node_id == "node-001"
        assert info.status == HealthStatus.UNKNOWN
        assert info.consecutive_failures == 0
        assert info.consecutive_successes == 0

    def test_record_check_success(self) -> None:
        """Test recording a successful check."""
        info = NodeHealthInfo(node_id="node-001")
        info.record_check(success=True, latency_ms=45)

        assert info.consecutive_successes == 1
        assert info.consecutive_failures == 0
        assert info.last_heartbeat is not None
        assert info.average_latency_ms == 45.0

    def test_record_check_failure(self) -> None:
        """Test recording a failed check."""
        info = NodeHealthInfo(node_id="node-001")
        info.record_check(success=False)

        assert info.consecutive_failures == 1
        assert info.consecutive_successes == 0
        assert info.total_failures == 1

    def test_record_check_exponential_moving_average(self) -> None:
        """Test latency exponential moving average."""
        info = NodeHealthInfo(node_id="node-001")
        info.record_check(success=True, latency_ms=100)
        info.record_check(success=True, latency_ms=50)

        # Should be between 50 and 100, closer to 50 due to EMA
        assert 50 < info.average_latency_ms < 100

    def test_update_status_healthy(self, sample_config: HealthConfig) -> None:
        """Test updating status to healthy."""
        info = NodeHealthInfo(node_id="node-001")
        info.record_check(success=True)
        status = info.update_status(sample_config)
        assert status == HealthStatus.HEALTHY

    def test_update_status_unhealthy_consecutive_failures(
        self, sample_config: HealthConfig
    ) -> None:
        """Test updating status to unhealthy due to consecutive failures."""
        info = NodeHealthInfo(node_id="node-001")
        for _ in range(sample_config.max_consecutive_failures):
            info.record_check(success=False)
        status = info.update_status(sample_config)
        assert status == HealthStatus.UNHEALTHY

    def test_update_status_degraded_old_heartbeat(
        self, sample_config: HealthConfig
    ) -> None:
        """Test updating status to degraded due to old heartbeat."""
        info = NodeHealthInfo(node_id="node-001")
        info.last_heartbeat = datetime.utcnow() - timedelta(
            seconds=sample_config.degraded_threshold + 1
        )
        status = info.update_status(sample_config)
        assert status == HealthStatus.DEGRADED

    def test_update_status_recovery(self, sample_config: HealthConfig) -> None:
        """Test status recovery after consecutive successes."""
        info = NodeHealthInfo(node_id="node-001")
        info.status = HealthStatus.UNHEALTHY
        info.consecutive_failures = 3

        # Record successful checks
        for _ in range(sample_config.recovery_threshold):
            info.record_check(success=True)

        status = info.update_status(sample_config)
        assert status == HealthStatus.HEALTHY


# ============================================================================
# HealthMonitorStats Tests
# ============================================================================


class TestHealthMonitorStats:
    """Tests for HealthMonitorStats."""

    def test_success_rate(self) -> None:
        """Test calculating success rate."""
        stats = HealthMonitorStats(
            total_checks=10,
            successful_checks=8,
            failed_checks=2,
        )
        assert stats.success_rate() == 80.0

    def test_success_rate_zero_checks(self) -> None:
        """Test success rate with zero checks."""
        stats = HealthMonitorStats(total_checks=0)
        assert stats.success_rate() == 0.0


# ============================================================================
# HealthMonitor Initialization Tests
# ============================================================================


class TestHealthMonitorInit:
    """Tests for HealthMonitor initialization."""

    def test_create_monitor_with_defaults(self) -> None:
        """Test creating monitor with defaults."""
        monitor = HealthMonitor()
        assert monitor.is_running is False
        assert monitor.config is not None
        assert monitor.registry is not None

    def test_create_monitor_with_config(self, sample_config: HealthConfig) -> None:
        """Test creating monitor with custom config."""
        monitor = HealthMonitor(config=sample_config)
        assert monitor.config == sample_config

    def test_create_monitor_with_registry(
        self, sample_registry: NodeRegistry
    ) -> None:
        """Test creating monitor with custom registry."""
        monitor = HealthMonitor(registry=sample_registry)
        assert monitor.registry == sample_registry


# ============================================================================
# HealthMonitor Lifecycle Tests
# ============================================================================


class TestHealthMonitorLifecycle:
    """Tests for health monitor lifecycle."""

    @pytest.mark.asyncio
    async def test_start_monitor(self, health_monitor: HealthMonitor) -> None:
        """Test starting the monitor."""
        await health_monitor.start()
        assert health_monitor.is_running is True
        await health_monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_monitor(self, health_monitor: HealthMonitor) -> None:
        """Test stopping the monitor."""
        await health_monitor.start()
        await health_monitor.stop()
        assert health_monitor.is_running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self, health_monitor: HealthMonitor) -> None:
        """Test starting already running monitor."""
        await health_monitor.start()
        await health_monitor.start()  # Should not error
        await health_monitor.stop()


# ============================================================================
# HealthMonitor Check Tests
# ============================================================================


class TestHealthMonitorCheck:
    """Tests for health checks."""

    @pytest.mark.asyncio
    async def test_check_health_success(self, health_monitor: HealthMonitor) -> None:
        """Test successful health check."""
        # Mock the health check to succeed
        with patch.object(
            health_monitor, "_perform_health_check", return_value=asyncio.sleep(0)
        ):
            status = await health_monitor.check_health("node-001")
            assert status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_health_node_not_found(
        self, health_monitor: HealthMonitor
    ) -> None:
        """Test checking health of non-existent node."""
        with pytest.raises(HealthCheckError, match="Node not found"):
            await health_monitor.check_health("nonexistent")

    @pytest.mark.asyncio
    async def test_check_health_timeout(self, health_monitor: HealthMonitor) -> None:
        """Test health check timeout."""
        # Mock a slow health check
        async def slow_check(node: Node) -> None:
            await asyncio.sleep(10)

        with patch.object(health_monitor, "_perform_health_check", side_effect=slow_check):
            # Update config to have short timeout
            health_monitor.config.check_timeout = 0.1

            with pytest.raises(HealthCheckError, match="timeout"):
                await health_monitor.check_health("node-001")

    @pytest.mark.asyncio
    async def test_get_health_info(self, health_monitor: HealthMonitor) -> None:
        """Test getting health info for a node."""
        # Perform a health check first
        with patch.object(
            health_monitor, "_perform_health_check", return_value=asyncio.sleep(0)
        ):
            await health_monitor.check_health("node-001")

        info = health_monitor.get_health_info("node-001")
        assert info is not None
        assert info.node_id == "node-001"


# ============================================================================
# HealthMonitor Statistics Tests
# ============================================================================


class TestHealthMonitorStats:
    """Tests for health monitor statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_initial(self, health_monitor: HealthMonitor) -> None:
        """Test getting initial stats."""
        stats = health_monitor.get_stats()
        assert stats.total_checks == 0
        assert stats.healthy_nodes == 0

    @pytest.mark.asyncio
    async def test_get_stats_after_checks(self, health_monitor: HealthMonitor) -> None:
        """Test getting stats after health checks."""
        with patch.object(
            health_monitor, "_perform_health_check", return_value=asyncio.sleep(0)
        ):
            await health_monitor.check_health("node-001")

        stats = health_monitor.get_stats()
        assert stats.total_checks > 0


# ============================================================================
# HealthMonitor Failure Detection Tests
# ============================================================================


class TestHealthMonitorFailureDetection:
    """Tests for failure detection."""

    @pytest.mark.asyncio
    async def test_detect_failures_force_check(
        self, health_monitor: HealthMonitor
    ) -> None:
        """Test detecting failures with force check."""
        with patch.object(
            health_monitor, "_perform_health_check", return_value=asyncio.sleep(0)
        ):
            failures = await health_monitor.detect_failures(force_check=True)

        # Should return dict, possibly empty
        assert isinstance(failures, dict)

    @pytest.mark.asyncio
    async def test_get_failed_nodes(self, health_monitor: HealthMonitor) -> None:
        """Test getting list of failed nodes."""
        with patch.object(
            health_monitor, "_perform_health_check", return_value=asyncio.sleep(0)
        ):
            failed = await health_monitor.get_failed_nodes()

        # Should return list
        assert isinstance(failed, list)


# ============================================================================
# HealthMonitor Failover Tests
# ============================================================================


class TestHealthMonitorFailover:
    """Tests for failover handling."""

    @pytest.mark.asyncio
    async def test_handle_failover_no_config(
        self, health_monitor: HealthMonitor
    ) -> None:
        """Test failover without work queue configured."""
        with pytest.raises(HealthCheckError, match="Work queue not configured"):
            await health_monitor.handle_failover()

    @pytest.mark.asyncio
    async def test_handle_failover_no_load_balancer(
        self, health_monitor: HealthMonitor
    ) -> None:
        """Test failover without load balancer configured."""
        from autoflow.coordination.work_queue import DistributedWorkQueue

        health_monitor.work_queue = DistributedWorkQueue()

        with pytest.raises(HealthCheckError, match="Load balancer not configured"):
            await health_monitor.handle_failover()


# ============================================================================
# NodeHealthInfo Edge Cases Tests
# ============================================================================


class TestNodeHealthInfoEdgeCases:
    """Tests for edge cases in NodeHealthInfo."""

    def test_record_check_without_latency(self) -> None:
        """Test recording check without latency."""
        info = NodeHealthInfo(node_id="node-001")
        info.record_check(success=True)
        # Should not error
        assert info.total_checks == 1

    def test_update_status_unknown_initial(self, sample_config: HealthConfig) -> None:
        """Test status is UNKNOWN initially."""
        info = NodeHealthInfo(node_id="node-001")
        status = info.update_status(sample_config)
        assert status == HealthStatus.UNKNOWN

    def test_update_status_with_timeout_heartbeat(
        self, sample_config: HealthConfig
    ) -> None:
        """Test status update with timed out heartbeat."""
        info = NodeHealthInfo(node_id="node-001")
        info.last_heartbeat = datetime.utcnow() - timedelta(
            seconds=sample_config.timeout_threshold + 10
        )
        status = info.update_status(sample_config)
        assert status == HealthStatus.UNHEALTHY

    def test_consecutive_successes_resets_on_failure(self) -> None:
        """Test that consecutive successes resets on failure."""
        info = NodeHealthInfo(node_id="node-001")
        info.record_check(success=True)
        info.record_check(success=True)
        assert info.consecutive_successes == 2

        info.record_check(success=False)
        assert info.consecutive_successes == 0
        assert info.consecutive_failures == 1


# ============================================================================
# HealthMonitor Edge Cases Tests
# ============================================================================


class TestHealthMonitorEdgeCases:
    """Tests for edge cases in HealthMonitor."""

    @pytest.mark.asyncio
    async def test_check_all_nodes_empty_registry(self) -> None:
        """Test checking all nodes with empty registry."""
        monitor = HealthMonitor(registry=NodeRegistry())
        statuses = await monitor.check_all_nodes()
        assert statuses == {}

    @pytest.mark.asyncio
    async def test_auto_failover_not_running(self, health_monitor: HealthMonitor) -> None:
        """Test auto failover when not running."""
        # Start briefly, then stop
        await health_monitor.start()
        await health_monitor.stop()

        # Auto failover should not run
        task = asyncio.create_task(health_monitor.auto_failover())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
