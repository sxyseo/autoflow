"""Integration Tests for Healing Orchestrator.

Tests the complete closed-loop self-healing workflow including monitoring, diagnosis,
healing actions, verification, rollback, and escalation. These tests ensure the
orchestrator can:
- Coordinate the complete healing workflow end-to-end
- Manage healing sessions and state transitions
- Log all events for transparency
- Handle escalation for unhealable conditions
- Execute rollback on failure
- Integrate all healing components properly
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from autoflow.healing.actions import (
    ActionRegistry,
    ActionStatus,
    ActionType,
    ActionResult,
    HealingAction,
    RollbackManager,
)
from autoflow.healing.config import HealingConfig
from autoflow.healing.diagnostic import (
    ConfidenceLevel,
    DiagnosticResult,
    FailureCategory,
    HealingPlan,
    HealingStrategy,
    RootCause,
    RootCauseAnalyzer,
    StrategySelector,
)
from autoflow.healing.monitor import (
    DegradationSignal,
    HealthAssessment,
    MetricReading,
    WorkflowHealthMonitor,
    WorkflowHealthStatus,
)
from autoflow.healing.orchestrator import (
    EscalationManager,
    HealingEvent,
    HealingEventLogger,
    HealingOrchestrator,
    HealingOutcome,
    HealingSession,
    OrchestratorState,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_config(tmp_path: Path) -> HealingConfig:
    """Create a sample healing configuration for testing."""
    config = HealingConfig(
        enabled=True,
        max_healing_attempts=3,
        healing_timeout=600,
        project_root=tmp_path,
    )
    return config


@pytest.fixture
def sample_root_cause() -> RootCause:
    """Create a sample root cause for testing."""
    return RootCause(
        category=FailureCategory.NETWORK_ISSUE,
        description="Network connectivity issues detected",
        evidence=["Connection timeout", "High latency"],
        confidence=ConfidenceLevel.HIGH,
        affected_components=["api_client", "database"],
        related_metrics=["network_latency", "connection_errors"],
        suggested_strategies=[HealingStrategy.RETRY],
    )


@pytest.fixture
def sample_diagnostic_result(sample_root_cause: RootCause) -> DiagnosticResult:
    """Create a sample diagnostic result for testing."""
    return DiagnosticResult(
        timestamp=datetime.now(),
        health_status=WorkflowHealthStatus.DEGRADED,
        root_causes=[sample_root_cause],
        primary_cause=sample_root_cause,
        degradation_signals=[],
        metadata={},
        healing_plan={},
        requires_escalation=False,
        analysis_duration=1.5,
    )


@pytest.fixture
def healthy_assessment() -> HealthAssessment:
    """Create a healthy health assessment."""
    return HealthAssessment(
        status=WorkflowHealthStatus.HEALTHY,
        timestamp=datetime.now(),
        metrics={"failure_rate": MetricReading(value=0.0, timestamp=datetime.now())},
        violations=[],
        recommendations=[],
    )


@pytest.fixture
def degraded_assessment() -> HealthAssessment:
    """Create a degraded health assessment."""
    return HealthAssessment(
        status=WorkflowHealthStatus.DEGRADED,
        timestamp=datetime.now(),
        metrics={
            "failure_rate": MetricReading(value=0.25, timestamp=datetime.now()),
            "execution_time": MetricReading(value=120.0, timestamp=datetime.now()),
        },
        violations=[
            {
                "metric_type": "task_failure_rate",
                "severity": "critical",
                "current_value": 0.25,
                "threshold_value": 0.1,
            }
        ],
        recommendations=["Investigate network connectivity"],
    )


@pytest.fixture
def sample_healing_plan() -> HealingPlan:
    """Create a sample healing plan."""
    action = HealingAction(
        action_type=ActionType.RETRY,
        name="Retry Failed Task",
        description="Retry with exponential backoff",
        severity="low",
        parameters={"max_retries": 3},
        preconditions=[],
        expected_outcome="Task succeeds",
        rollback_strategy="Reset counter",
        timeout=300,
        requires_approval=False,
    )

    return HealingPlan(
        selected_strategy=HealingStrategy.RETRY,
        fallback_strategies=[HealingStrategy.ESCALATE],
        execution_steps=[action],
        rollback_plan=[],
        verification_steps=["Check task status"],
        estimated_duration=60.0,
        resource_requirements={"cpu": "low"},
        risk_assessment={"risk_level": "low"},
    )


@pytest.fixture
def workflow_monitor(sample_config: HealingConfig) -> WorkflowHealthMonitor:
    """Create a workflow health monitor."""
    return WorkflowHealthMonitor(config=sample_config)


@pytest.fixture
def root_cause_analyzer(sample_config: HealingConfig) -> RootCauseAnalyzer:
    """Create a root cause analyzer."""
    return RootCauseAnalyzer(config=sample_config)


@pytest.fixture
def strategy_selector(sample_config: HealingConfig) -> StrategySelector:
    """Create a strategy selector."""
    return StrategySelector(config=sample_config)


@pytest.fixture
def action_registry() -> ActionRegistry:
    """Create an action registry with mock executors."""
    registry = ActionRegistry()

    # Create mock executor
    mock_executor = MagicMock()
    mock_executor.execute_action = AsyncMock(
        return_value=ActionResult(
            status=ActionStatus.COMPLETED,
            success=True,
            message="Action completed successfully",
            execution_time=1.0,
            changes_made=[],
            verification_passed=True,
            can_rollback=True,
            metadata={},
        )
    )

    registry.register_executor(ActionType.RETRY, mock_executor)
    return registry


@pytest.fixture
def rollback_manager(tmp_path: Path) -> RollbackManager:
    """Create a rollback manager."""
    return RollbackManager(project_root=tmp_path)


@pytest.fixture
def healing_orchestrator(
    sample_config: HealingConfig,
    workflow_monitor: WorkflowHealthMonitor,
    root_cause_analyzer: RootCauseAnalyzer,
    strategy_selector: StrategySelector,
    action_registry: ActionRegistry,
    rollback_manager: RollbackManager,
) -> HealingOrchestrator:
    """Create a healing orchestrator with all dependencies."""
    return HealingOrchestrator(
        config=sample_config,
        monitor=workflow_monitor,
        analyzer=root_cause_analyzer,
        selector=strategy_selector,
        registry=action_registry,
        rollback_manager=rollback_manager,
    )


# ============================================================================
# Enum Tests
# ============================================================================


class TestOrchestratorState:
    """Tests for OrchestratorState enum."""

    def test_orchestrator_state_values(self) -> None:
        """Test OrchestratorState enum values."""
        assert OrchestratorState.IDLE.value == "idle"
        assert OrchestratorState.MONITORING.value == "monitoring"
        assert OrchestratorState.DIAGNOSING.value == "diagnosing"
        assert OrchestratorState.HEALING.value == "healing"
        assert OrchestratorState.VERIFYING.value == "verifying"
        assert OrchestratorState.ESCALATING.value == "escalating"
        assert OrchestratorState.PAUSED.value == "paused"

    def test_orchestrator_state_is_string(self) -> None:
        """Test that state values are strings."""
        assert isinstance(OrchestratorState.IDLE.value, str)


class TestHealingOutcome:
    """Tests for HealingOutcome enum."""

    def test_healing_outcome_values(self) -> None:
        """Test HealingOutcome enum values."""
        assert HealingOutcome.HEALED.value == "healed"
        assert HealingOutcome.FAILED.value == "failed"
        assert HealingOutcome.ROLLED_BACK.value == "rolled_back"
        assert HealingOutcome.ESCALATED.value == "escalated"
        assert HealingOutcome.SKIPPED.value == "skipped"

    def test_healing_outcome_is_string(self) -> None:
        """Test that outcome values are strings."""
        assert isinstance(HealingOutcome.HEALED.value, str)


# ============================================================================
# Data Model Tests
# ============================================================================


class TestHealingEvent:
    """Tests for HealingEvent dataclass."""

    def test_healing_event_init(self, sample_diagnostic_result: DiagnosticResult) -> None:
        """Test HealingEvent initialization."""
        event = HealingEvent(
            event_id="event-001",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.MONITORING,
            event_type="degradation_detected",
            severity="warning",
            health_status=WorkflowHealthStatus.DEGRADED,
            description="Degradation detected in workflow",
            metadata={"metric": "failure_rate"},
            diagnostic_result=sample_diagnostic_result,
        )

        assert event.event_id == "event-001"
        assert event.orchestrator_state == OrchestratorState.MONITORING
        assert event.event_type == "degradation_detected"
        assert event.severity == "warning"
        assert event.diagnostic_result == sample_diagnostic_result
        assert event.outcome is None

    def test_healing_event_to_dict(
        self, sample_diagnostic_result: DiagnosticResult, sample_healing_plan: HealingPlan
    ) -> None:
        """Test HealingEvent to_dict method."""
        action = sample_healing_plan.execution_steps[0]
        action_result = ActionResult(
            status=ActionStatus.COMPLETED,
            success=True,
            message="Success",
            execution_time=1.0,
        )

        event = HealingEvent(
            event_id="event-002",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.HEALING,
            event_type="action_completed",
            severity="info",
            health_status=WorkflowHealthStatus.HEALTHY,
            description="Action completed",
            healing_action=action,
            action_result=action_result,
            outcome=HealingOutcome.HEALED,
        )

        event_dict = event.to_dict()

        assert event_dict["event_id"] == "event-002"
        assert event_dict["orchestrator_state"] == "healing"
        assert event_dict["event_type"] == "action_completed"
        assert event_dict["outcome"] == "healed"
        assert event_dict["healing_action"] is not None
        assert event_dict["action_result"] is not None


class TestHealingSession:
    """Tests for HealingSession dataclass."""

    def test_healing_session_init(self, healthy_assessment: HealthAssessment) -> None:
        """Test HealingSession initialization."""
        session = HealingSession(
            session_id="session-001",
            start_time=datetime.now(),
            initial_assessment=healthy_assessment,
            events=[],
            final_outcome=None,
            healing_attempts=0,
        )

        assert session.session_id == "session-001"
        assert session.initial_assessment == healthy_assessment
        assert session.end_time is None
        assert session.final_outcome is None
        assert session.healing_attempts == 0

    def test_healing_session_to_dict(
        self, healthy_assessment: HealthAssessment, sample_diagnostic_result: DiagnosticResult
    ) -> None:
        """Test HealingSession to_dict method."""
        event = HealingEvent(
            event_id="event-001",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.MONITORING,
            event_type="test",
            severity="info",
            health_status=WorkflowHealthStatus.HEALTHY,
            description="Test event",
        )

        session = HealingSession(
            session_id="session-002",
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=5),
            initial_assessment=healthy_assessment,
            events=[event],
            final_outcome=HealingOutcome.HEALED,
            healing_attempts=2,
        )

        session_dict = session.to_dict()

        assert session_dict["session_id"] == "session-002"
        assert session_dict["end_time"] is not None
        assert session_dict["final_outcome"] == "healed"
        assert session_dict["healing_attempts"] == 2
        assert len(session_dict["events"]) == 1


# ============================================================================
# HealingEventLogger Tests
# ============================================================================


class TestHealingEventLogger:
    """Tests for HealingEventLogger."""

    def test_init(self, tmp_path: Path) -> None:
        """Test HealingEventLogger initialization."""
        logger = HealingEventLogger(log_dir=tmp_path / "logs")

        assert logger.log_dir == tmp_path / "logs"
        assert logger.log_dir.exists()
        assert len(logger._current_events) == 0

    def test_log_event(self, tmp_path: Path) -> None:
        """Test logging an event."""
        event_logger = HealingEventLogger(log_dir=tmp_path / "logs")

        event = HealingEvent(
            event_id="event-001",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.MONITORING,
            event_type="test",
            severity="info",
            health_status=WorkflowHealthStatus.HEALTHY,
            description="Test event",
        )

        event_logger.log_event(event)

        assert len(event_logger._current_events) == 1
        assert event_logger._current_events[0] == event

    def test_persist_events(self, tmp_path: Path) -> None:
        """Test persisting events to disk."""
        event_logger = HealingEventLogger(log_dir=tmp_path / "logs")

        event = HealingEvent(
            event_id="event-001",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.HEALING,
            event_type="test",
            severity="info",
            health_status=WorkflowHealthStatus.HEALTHY,
            description="Test event",
        )

        event_logger.log_event(event)
        log_file = event_logger.persist_events("session-001")

        assert log_file.exists()
        assert log_file.name == "session_session-001.json"
        assert len(event_logger._current_events) == 0  # Cleared after persist

    def test_get_events_current(self, tmp_path: Path) -> None:
        """Test getting current events."""
        event_logger = HealingEventLogger(log_dir=tmp_path / "logs")

        event = HealingEvent(
            event_id="event-001",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.IDLE,
            event_type="test",
            severity="info",
            health_status=WorkflowHealthStatus.HEALTHY,
            description="Test event",
        )

        event_logger.log_event(event)
        events = event_logger.get_events()

        assert len(events) == 1
        assert events[0].event_id == "event-001"

    def test_get_events_by_session(self, tmp_path: Path) -> None:
        """Test getting events by session ID."""
        event_logger = HealingEventLogger(log_dir=tmp_path / "logs")

        event = HealingEvent(
            event_id="event-001",
            timestamp=datetime.now(),
            orchestrator_state=OrchestratorState.IDLE,
            event_type="test",
            severity="info",
            health_status=WorkflowHealthStatus.HEALTHY,
            description="Test event",
        )

        event_logger.log_event(event)
        event_logger.persist_events("session-001")

        events = event_logger.get_events(session_id="session-001")
        assert len(events) == 1


# ============================================================================
# EscalationManager Tests
# ============================================================================


class TestEscalationManager:
    """Tests for EscalationManager."""

    def test_init(self, sample_config: HealingConfig) -> None:
        """Test EscalationManager initialization."""
        manager = EscalationManager(config=sample_config)

        assert manager.config == sample_config
        assert len(manager._escalations) == 0

    def test_should_escalate_max_attempts(
        self, sample_config: HealingConfig, sample_diagnostic_result: DiagnosticResult
    ) -> None:
        """Test escalation when max attempts reached."""
        manager = EscalationManager(config=sample_config)

        # Max attempts is 3
        assert manager.should_escalate(3, sample_diagnostic_result) is True
        assert manager.should_escalate(2, sample_diagnostic_result) is False

    def test_should_escalate_requires_escalation(
        self, sample_config: HealingConfig, sample_root_cause: RootCause
    ) -> None:
        """Test escalation when diagnostic requires it."""
        manager = EscalationManager(config=sample_config)

        diagnostic_result = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=True,  # Requires escalation
            analysis_duration=1.0,
        )

        assert manager.should_escalate(0, diagnostic_result) is True

    def test_create_escalation(
        self,
        sample_config: HealingConfig,
        sample_diagnostic_result: DiagnosticResult,
        degraded_assessment: HealthAssessment,
    ) -> None:
        """Test creating an escalation record."""
        manager = EscalationManager(config=sample_config)

        escalation = manager.create_escalation(
            "session-001", sample_diagnostic_result, degraded_assessment
        )

        assert escalation["escalation_id"] == "escal_session-001"
        assert escalation["session_id"] == "session-001"
        assert escalation["severity"] == "degraded"
        assert "Root cause:" in escalation["summary"]
        assert len(escalation["root_causes"]) > 0
        assert len(escalation["recommended_actions"]) > 0
        assert escalation["status"] == "open"

    def test_get_escalation(
        self,
        sample_config: HealingConfig,
        sample_diagnostic_result: DiagnosticResult,
        degraded_assessment: HealthAssessment,
    ) -> None:
        """Test retrieving an escalation record."""
        manager = EscalationManager(config=sample_config)

        manager.create_escalation("session-001", sample_diagnostic_result, degraded_assessment)
        escalation = manager.get_escalation("session-001")

        assert escalation is not None
        assert escalation["session_id"] == "session-001"

    def test_get_escalation_not_found(self, sample_config: HealingConfig) -> None:
        """Test retrieving non-existent escalation."""
        manager = EscalationManager(config=sample_config)
        escalation = manager.get_escalation("non-existent")

        assert escalation is None


# ============================================================================
# HealingOrchestrator Initialization Tests
# ============================================================================


class TestHealingOrchestratorInit:
    """Tests for HealingOrchestrator initialization."""

    def test_init(
        self,
        sample_config: HealingConfig,
        workflow_monitor: WorkflowHealthMonitor,
        root_cause_analyzer: RootCauseAnalyzer,
        strategy_selector: StrategySelector,
        action_registry: ActionRegistry,
        rollback_manager: RollbackManager,
    ) -> None:
        """Test HealingOrchestrator initialization."""
        orchestrator = HealingOrchestrator(
            config=sample_config,
            monitor=workflow_monitor,
            analyzer=root_cause_analyzer,
            selector=strategy_selector,
            registry=action_registry,
            rollback_manager=rollback_manager,
        )

        assert orchestrator.config == sample_config
        assert orchestrator.monitor == workflow_monitor
        assert orchestrator.analyzer == root_cause_analyzer
        assert orchestrator.selector == strategy_selector
        assert orchestrator.registry == action_registry
        assert orchestrator.rollback_manager == rollback_manager
        assert orchestrator.state == OrchestratorState.IDLE
        assert orchestrator._current_session is None
        assert orchestrator._session_counter == 0

    def test_get_state(
        self, healing_orchestrator: HealingOrchestrator
    ) -> None:
        """Test getting orchestrator state."""
        assert healing_orchestrator.get_state() == OrchestratorState.IDLE

    def test_get_current_session(
        self, healing_orchestrator: HealingOrchestrator
    ) -> None:
        """Test getting current session when none exists."""
        assert healing_orchestrator.get_current_session() is None


# ============================================================================
# Healing Cycle Integration Tests
# ============================================================================


class TestHealingCycleIntegration:
    """Integration tests for complete healing cycles."""

    @pytest.mark.asyncio
    async def test_full_healing_cycle_success(
        self,
        healing_orchestrator: HealingOrchestrator,
        degraded_assessment: HealthAssessment,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
    ) -> None:
        """Test a complete successful healing cycle."""
        # Mock the dependencies
        healing_orchestrator.monitor.assess_health = Mock(return_value=degraded_assessment)
        healing_orchestrator.analyzer.analyze_failure = AsyncMock(
            return_value=sample_diagnostic_result
        )
        healing_orchestrator.selector.select_healing_strategy = Mock(
            return_value=sample_healing_plan
        )

        # Run the healing cycle
        outcome = await healing_orchestrator.run_healing_cycle(
            trigger_assessment=degraded_assessment
        )

        # Verify the outcome
        assert outcome == HealingOutcome.HEALED
        assert healing_orchestrator.state == OrchestratorState.IDLE

        # Verify session was created and completed
        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert session.final_outcome == HealingOutcome.HEALED
        assert session.healing_attempts > 0

    @pytest.mark.asyncio
    async def test_healing_cycle_healthy_workflow(
        self,
        healing_orchestrator: HealingOrchestrator,
        healthy_assessment: HealthAssessment,
    ) -> None:
        """Test healing cycle when workflow is already healthy."""
        healing_orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)

        outcome = await healing_orchestrator.run_healing_cycle(
            trigger_assessment=healthy_assessment
        )

        assert outcome == HealingOutcome.SKIPPED
        assert healing_orchestrator.state == OrchestratorState.IDLE

    @pytest.mark.asyncio
    async def test_healing_cycle_diagnosis_failure(
        self,
        healing_orchestrator: HealingOrchestrator,
        degraded_assessment: HealthAssessment,
    ) -> None:
        """Test healing cycle when diagnosis fails."""
        healing_orchestrator.monitor.assess_health = Mock(return_value=degraded_assessment)
        healing_orchestrator.analyzer.analyze_failure = AsyncMock(return_value=None)

        outcome = await healing_orchestrator.run_healing_cycle(
            trigger_assessment=degraded_assessment
        )

        assert outcome == HealingOutcome.ESCALATED

    @pytest.mark.asyncio
    async def test_healing_cycle_with_escalation(
        self,
        sample_config: HealingConfig,
        workflow_monitor: WorkflowHealthMonitor,
        root_cause_analyzer: RootCauseAnalyzer,
        strategy_selector: StrategySelector,
        action_registry: ActionRegistry,
        rollback_manager: RollbackManager,
        degraded_assessment: HealthAssessment,
        sample_root_cause: RootCause,
    ) -> None:
        """Test healing cycle that escalates."""
        # Create diagnostic result that requires escalation
        escalation_diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=True,  # Requires escalation
            analysis_duration=1.0,
        )

        orchestrator = HealingOrchestrator(
            config=sample_config,
            monitor=workflow_monitor,
            analyzer=root_cause_analyzer,
            selector=strategy_selector,
            registry=action_registry,
            rollback_manager=rollback_manager,
        )

        orchestrator.monitor.assess_health = Mock(return_value=degraded_assessment)
        orchestrator.analyzer.analyze_failure = AsyncMock(return_value=escalation_diagnostic)

        outcome = await orchestrator.run_healing_cycle(
            trigger_assessment=degraded_assessment
        )

        assert outcome == HealingOutcome.ESCALATED

        # Verify escalation was created
        escalation = orchestrator.escalation_manager.get_escalation(
            orchestrator._current_session.session_id
        )
        assert escalation is not None


# ============================================================================
# Monitoring Phase Tests
# ============================================================================


class TestMonitoringPhase:
    """Tests for the monitoring phase."""

    @pytest.mark.asyncio
    async def test_monitor_phase_with_assessment(
        self,
        healing_orchestrator: HealingOrchestrator,
        degraded_assessment: HealthAssessment,
    ) -> None:
        """Test monitoring phase with provided assessment."""
        assessment = await healing_orchestrator._monitor_phase(degraded_assessment)

        assert assessment == degraded_assessment
        assert healing_orchestrator.state == OrchestratorState.MONITORING

        # Verify event was logged
        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert len(session.events) > 0
        assert session.events[0].event_type == "monitoring_started"

    @pytest.mark.asyncio
    async def test_monitor_phase_without_assessment(
        self, healing_orchestrator: HealingOrchestrator, healthy_assessment: HealthAssessment
    ) -> None:
        """Test monitoring phase without provided assessment."""
        healing_orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)

        assessment = await healing_orchestrator._monitor_phase(None)

        assert assessment == healthy_assessment
        assert healing_orchestrator.state == OrchestratorState.MONITORING


# ============================================================================
# Diagnosis Phase Tests
# ============================================================================


class TestDiagnosisPhase:
    """Tests for the diagnosis phase."""

    @pytest.mark.asyncio
    async def test_diagnosis_phase_success(
        self,
        healing_orchestrator: HealingOrchestrator,
        degraded_assessment: HealthAssessment,
        sample_diagnostic_result: DiagnosticResult,
    ) -> None:
        """Test successful diagnosis phase."""
        healing_orchestrator.analyzer.analyze_failure = AsyncMock(
            return_value=sample_diagnostic_result
        )

        result = await healing_orchestrator._diagnosis_phase(degraded_assessment)

        assert result == sample_diagnostic_result
        assert healing_orchestrator.state == OrchestratorState.DIAGNOSING

        # Verify events were logged
        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert any(e.event_type == "diagnosis_started" for e in session.events)
        assert any(e.event_type == "diagnosis_completed" for e in session.events)


# ============================================================================
# Healing Phase Tests
# ============================================================================


class TestHealingPhase:
    """Tests for the healing phase."""

    @pytest.mark.asyncio
    async def test_healing_phase_success(
        self,
        healing_orchestrator: HealingOrchestrator,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
    ) -> None:
        """Test successful healing phase."""
        healthy_assessment = HealthAssessment(
            status=WorkflowHealthStatus.HEALTHY,
            timestamp=datetime.now(),
            metrics={},
            violations=[],
            recommendations=[],
        )

        healing_orchestrator.selector.select_healing_strategy = Mock(
            return_value=sample_healing_plan
        )
        healing_orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)

        outcome = await healing_orchestrator._healing_phase(
            sample_diagnostic_result, sample_diagnostic_result
        )

        assert outcome == HealingOutcome.HEALED

    @pytest.mark.asyncio
    async def test_execute_action_success(
        self,
        healing_orchestrator: HealingOrchestrator,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
    ) -> None:
        """Test executing a single action successfully."""
        action = sample_healing_plan.execution_steps[0]

        healthy_assessment = HealthAssessment(
            status=WorkflowHealthStatus.HEALTHY,
            timestamp=datetime.now(),
            metrics={},
            violations=[],
            recommendations=[],
        )

        healing_orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)

        outcome = await healing_orchestrator._execute_action(action, sample_diagnostic_result)

        assert outcome == HealingOutcome.HEALED

        # Verify events were logged
        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert any(e.event_type == "action_started" for e in session.events)
        assert any(e.event_type == "action_completed" for e in session.events)

    @pytest.mark.asyncio
    async def test_execute_action_failure_with_rollback(
        self,
        sample_config: HealingConfig,
        workflow_monitor: WorkflowHealthMonitor,
        root_cause_analyzer: RootCauseAnalyzer,
        strategy_selector: StrategySelector,
        rollback_manager: RollbackManager,
        degraded_assessment: HealthAssessment,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
    ) -> None:
        """Test action failure with rollback."""
        # Create registry with failing executor
        failing_registry = ActionRegistry()
        mock_executor = MagicMock()
        mock_executor.execute_action = AsyncMock(
            return_value=ActionResult(
                status=ActionStatus.FAILED,
                success=False,
                message="Action failed",
                execution_time=1.0,
                changes_made=[],
                verification_passed=False,
                can_rollback=True,
                metadata={},
            )
        )
        failing_registry.register_executor(ActionType.RETRY, mock_executor)

        orchestrator = HealingOrchestrator(
            config=sample_config,
            monitor=workflow_monitor,
            analyzer=root_cause_analyzer,
            selector=strategy_selector,
            registry=failing_registry,
            rollback_manager=rollback_manager,
        )

        action = sample_healing_plan.execution_steps[0]

        # Create a checkpoint for rollback
        await rollback_manager.create_checkpoint(
            action.id, {"state": "before_action"}
        )

        outcome = await orchestrator._execute_action(action, sample_diagnostic_result)

        assert outcome == HealingOutcome.ROLLED_BACK


# ============================================================================
# Verification Phase Tests
# ============================================================================


class TestVerificationPhase:
    """Tests for the verification phase."""

    @pytest.mark.asyncio
    async def test_verification_passed(
        self,
        healing_orchestrator: HealingOrchestrator,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
    ) -> None:
        """Test verification when workflow is healthy."""
        healthy_assessment = HealthAssessment(
            status=WorkflowHealthStatus.HEALTHY,
            timestamp=datetime.now(),
            metrics={},
            violations=[],
            recommendations=[],
        )

        healing_orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)

        action = sample_healing_plan.execution_steps[0]
        action_result = ActionResult(
            status=ActionStatus.COMPLETED,
            success=True,
            message="Success",
            execution_time=1.0,
        )

        outcome = await healing_orchestrator._verify_action(action, action_result)

        assert outcome == HealingOutcome.HEALED
        assert healing_orchestrator.state == OrchestratorState.VERIFYING

    @pytest.mark.asyncio
    async def test_verification_failed_escalates(
        self,
        sample_config: HealingConfig,
        workflow_monitor: WorkflowHealthMonitor,
        root_cause_analyzer: RootCauseAnalyzer,
        strategy_selector: StrategySelector,
        action_registry: ActionRegistry,
        rollback_manager: RollbackManager,
        degraded_assessment: HealthAssessment,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
    ) -> None:
        """Test verification fails and escalates after max attempts."""
        orchestrator = HealingOrchestrator(
            config=sample_config,
            monitor=workflow_monitor,
            analyzer=root_cause_analyzer,
            selector=strategy_selector,
            registry=action_registry,
            rollback_manager=rollback_manager,
        )

        # Still degraded after action
        orchestrator.monitor.assess_health = Mock(return_value=degraded_assessment)

        # Set healing attempts to max to trigger escalation
        if orchestrator._current_session:
            orchestrator._current_session.healing_attempts = 3

        action = sample_healing_plan.execution_steps[0]
        action_result = ActionResult(
            status=ActionStatus.COMPLETED,
            success=True,
            message="Success",
            execution_time=1.0,
        )

        outcome = await orchestrator._verify_action(action, action_result)

        assert outcome == HealingOutcome.ESCALATED


# ============================================================================
# Rollback Tests
# ============================================================================


class TestRollback:
    """Tests for rollback functionality."""

    @pytest.mark.asyncio
    async def test_rollback_success(
        self,
        healing_orchestrator: HealingOrchestrator,
        sample_diagnostic_result: DiagnosticResult,
        sample_healing_plan: HealingPlan,
        rollback_manager: RollbackManager,
    ) -> None:
        """Test successful rollback."""
        action = sample_healing_plan.execution_steps[0]

        # Create a checkpoint
        await rollback_manager.create_checkpoint(action.id, {"state": "before"})

        action_result = ActionResult(
            status=ActionStatus.FAILED,
            success=False,
            message="Failed",
            execution_time=1.0,
            can_rollback=True,
        )

        outcome = await healing_orchestrator._rollback_action(action, action_result)

        assert outcome == HealingOutcome.ROLLED_BACK

        # Verify rollback events were logged
        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert any(e.event_type == "rollback_started" for e in session.events)
        assert any(e.event_type == "rollback_completed" for e in session.events)


# ============================================================================
# Session Management Tests
# ============================================================================


class TestSessionManagement:
    """Tests for session management."""

    def test_create_session(
        self, healing_orchestrator: HealingOrchestrator, healthy_assessment: HealthAssessment
    ) -> None:
        """Test creating a new session."""
        session = healing_orchestrator._create_session(healthy_assessment)

        assert session.session_id.startswith("session_1_")
        assert session.initial_assessment == healthy_assessment
        assert session.start_time is not None
        assert session.end_time is None
        assert session.final_outcome is None

    def test_complete_session(
        self, healing_orchestrator: HealingOrchestrator, healthy_assessment: HealthAssessment
    ) -> None:
        """Test completing a session."""
        healing_orchestrator._create_session(healthy_assessment)

        outcome = healing_orchestrator._complete_session(HealingOutcome.HEALED)

        assert outcome == HealingOutcome.HEALED
        assert healing_orchestrator.state == OrchestratorState.IDLE

        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert session.end_time is not None
        assert session.final_outcome == HealingOutcome.HEALED


# ============================================================================
# Event Logging Tests
# ============================================================================


class TestEventLogging:
    """Tests for event logging within orchestrator."""

    @pytest.mark.asyncio
    async def test_log_event_creates_event(
        self, healing_orchestrator: HealingOrchestrator, healthy_assessment: HealthAssessment
    ) -> None:
        """Test that logging an event creates it properly."""
        healing_orchestrator._create_session(healthy_assessment)

        healing_orchestrator._log_event(
            event_type="test_event",
            severity="info",
            description="Test event description",
        )

        session = healing_orchestrator.get_current_session()
        assert session is not None
        assert len(session.events) == 1
        assert session.events[0].event_type == "test_event"

    @pytest.mark.asyncio
    async def test_events_persisted_after_cycle(
        self,
        healing_orchestrator: HealingOrchestrator,
        healthy_assessment: HealthAssessment,
        sample_config: HealingConfig,
    ) -> None:
        """Test that events are persisted after healing cycle."""
        log_dir = sample_config.project_root / ".auto-claude" / "healing" / "logs"

        healing_orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)

        await healing_orchestrator.run_healing_cycle(trigger_assessment=healthy_assessment)

        # Check that log file was created
        session = healing_orchestrator.get_current_session()
        assert session is not None

        log_file = log_dir / f"session_{session.session_id}.json"
        assert log_file.exists()


# ============================================================================
# End-to-End Integration Tests
# ============================================================================


class TestEndToEndIntegration:
    """End-to-end integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_degraded_to_healthy_workflow(
        self,
        sample_config: HealingConfig,
        workflow_monitor: WorkflowHealthMonitor,
        root_cause_analyzer: RootCauseAnalyzer,
        strategy_selector: StrategySelector,
        action_registry: ActionRegistry,
        rollback_manager: RollbackManager,
        degraded_assessment: HealthAssessment,
        sample_root_cause: RootCause,
    ) -> None:
        """Test complete workflow from degraded to healthy state."""
        orchestrator = HealingOrchestrator(
            config=sample_config,
            monitor=workflow_monitor,
            analyzer=root_cause_analyzer,
            selector=strategy_selector,
            registry=action_registry,
            rollback_manager=rollback_manager,
        )

        # Create diagnostic result
        diagnostic_result = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        # Mock the workflow
        healthy_assessment = HealthAssessment(
            status=WorkflowHealthStatus.HEALTHY,
            timestamp=datetime.now(),
            metrics={},
            violations=[],
            recommendations=[],
        )

        orchestrator.monitor.assess_health = Mock(return_value=healthy_assessment)
        orchestrator.analyzer.analyze_failure = AsyncMock(return_value=diagnostic_result)

        # Run healing cycle
        outcome = await orchestrator.run_healing_cycle(
            trigger_assessment=degraded_assessment
        )

        # Verify complete workflow
        assert outcome == HealingOutcome.HEALED

        session = orchestrator.get_current_session()
        assert session is not None
        assert session.final_outcome == HealingOutcome.HEALED
        assert len(session.events) > 0

        # Verify state transitions
        event_types = [e.event_type for e in session.events]
        assert "healing_cycle_started" in event_types
        assert "monitoring_started" in event_types
        assert "diagnosis_started" in event_types
        assert "session_completed" in event_types

    @pytest.mark.asyncio
    async def test_multiple_healing_attempts_then_escalation(
        self,
        sample_config: HealingConfig,
        workflow_monitor: WorkflowHealthMonitor,
        root_cause_analyzer: RootCauseAnalyzer,
        strategy_selector: StrategySelector,
        rollback_manager: RollbackManager,
        degraded_assessment: HealthAssessment,
        sample_root_cause: RootCause,
    ) -> None:
        """Test workflow that requires multiple attempts then escalates."""
        # Create registry with executor that always fails
        failing_registry = ActionRegistry()
        mock_executor = MagicMock()
        mock_executor.execute_action = AsyncMock(
            return_value=ActionResult(
                status=ActionStatus.FAILED,
                success=False,
                message="Action failed",
                execution_time=1.0,
                changes_made=[],
                verification_passed=False,
                can_rollback=False,
                metadata={},
            )
        )
        failing_registry.register_executor(ActionType.RETRY, mock_executor)

        orchestrator = HealingOrchestrator(
            config=sample_config,
            monitor=workflow_monitor,
            analyzer=root_cause_analyzer,
            selector=strategy_selector,
            registry=failing_registry,
            rollback_manager=rollback_manager,
        )

        diagnostic_result = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        orchestrator.monitor.assess_health = Mock(return_value=degraded_assessment)
        orchestrator.analyzer.analyze_failure = AsyncMock(return_value=diagnostic_result)

        # Run healing cycle - should fail and eventually escalate
        outcome = await orchestrator.run_healing_cycle(
            trigger_assessment=degraded_assessment
        )

        # Should escalate after max attempts
        assert outcome == HealingOutcome.ESCALATED

        session = orchestrator.get_current_session()
        assert session is not None
        assert session.healing_attempts >= sample_config.max_healing_attempts
