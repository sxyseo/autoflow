"""Healing orchestrator for closed-loop self-healing workflows.

This module provides the orchestrator that coordinates the complete self-healing workflow:
monitoring for degradation, diagnosing root causes, executing healing actions, and
verifying results. It implements a closed-loop system with transparency logging and
escalation paths for unhealable conditions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from autoflow.healing.recovery_learner import RecoveryLearner, RecoveryOutcome

if TYPE_CHECKING:
    from autoflow.healing.actions import (
        ActionRegistry,
        ActionResult,
        HealingAction,
        RollbackManager,
    )
    from autoflow.healing.config import HealingConfig
    from autoflow.healing.diagnostic import (
        DiagnosticResult,
        HealingPlan,
        RootCause,
        RootCauseAnalyzer,
        StrategySelector,
    )
    from autoflow.healing.monitor import (
        DegradationSignal,
        HealthAssessment,
        WorkflowHealthMonitor,
    )
    from autoflow.healing.recovery_learner import RecoveryLearner

# Runtime import for WorkflowHealthStatus (needed outside type hints)
from autoflow.healing.monitor import WorkflowHealthStatus


logger = logging.getLogger(__name__)


class OrchestratorState(Enum):
    """States of the healing orchestrator."""

    IDLE = "idle"
    MONITORING = "monitoring"
    DIAGNOSING = "diagnosing"
    HEALING = "healing"
    VERIFYING = "verifying"
    ESCALATING = "escalating"
    PAUSED = "paused"


class HealingOutcome(Enum):
    """Possible outcomes of a healing attempt."""

    HEALED = "healed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


@dataclass
class HealingEvent:
    """A single healing event for transparency logging.

    Attributes:
        event_id: Unique identifier for the event.
        timestamp: When the event occurred.
        orchestrator_state: State of the orchestrator during the event.
        event_type: Type of event (e.g., "degradation_detected", "healing_started").
        severity: Severity level of the event.
        health_status: Health status at the time of the event.
        description: Human-readable description of the event.
        metadata: Additional event metadata.
        diagnostic_result: Diagnostic result if available.
        healing_action: Healing action taken if applicable.
        action_result: Result of healing action if available.
        outcome: Final outcome of the healing attempt.
    """

    event_id: str
    timestamp: datetime
    orchestrator_state: OrchestratorState
    event_type: str
    severity: str
    health_status: WorkflowHealthStatus
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostic_result: DiagnosticResult | None = None
    healing_action: HealingAction | None = None
    action_result: ActionResult | None = None
    outcome: HealingOutcome | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary.

        Returns:
            Dictionary representation of the event.
        """
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "orchestrator_state": self.orchestrator_state.value,
            "event_type": self.event_type,
            "severity": self.severity,
            "health_status": self.health_status.value,
            "description": self.description,
            "metadata": self.metadata,
            "diagnostic_result": self.diagnostic_result.to_dict() if self.diagnostic_result else None,
            "healing_action": self.healing_action.to_dict() if self.healing_action else None,
            "action_result": self.action_result.to_dict() if self.action_result else None,
            "outcome": self.outcome.value if self.outcome else None,
        }


@dataclass
class HealingSession:
    """A complete healing session from detection to resolution.

    Attributes:
        session_id: Unique identifier for the session.
        start_time: When the session started.
        end_time: When the session ended (None if in progress).
        initial_assessment: Health assessment that triggered the session.
        events: List of events that occurred during the session.
        final_outcome: Final outcome of the session (None if in progress).
        healing_attempts: Number of healing attempts made.
    """

    session_id: str
    start_time: datetime
    end_time: datetime | None = None
    initial_assessment: HealthAssessment | None = None
    events: list[HealingEvent] = field(default_factory=list)
    final_outcome: HealingOutcome | None = None
    healing_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary.

        Returns:
            Dictionary representation of the session.
        """
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "initial_assessment": self.initial_assessment.to_dict() if self.initial_assessment else None,
            "events": [event.to_dict() for event in self.events],
            "final_outcome": self.final_outcome.value if self.final_outcome else None,
            "healing_attempts": self.healing_attempts,
        }


class HealingEventLogger:
    """Logger for healing events to maintain transparency.

    This class manages the logging of all healing events for audit trails
    and transparency. It persists events to disk and provides querying
    capabilities.
    """

    def __init__(self, log_dir: Path) -> None:
        """Initialize the event logger.

        Args:
            log_dir: Directory to store event logs.
        """
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_events: list[HealingEvent] = []

    def log_event(self, event: HealingEvent) -> None:
        """Log a healing event.

        Args:
            event: The event to log.
        """
        self._current_events.append(event)
        logger.info(
            f"Healing event: {event.event_type} - {event.description} "
            f"(state={event.orchestrator_state.value}, severity={event.severity})"
        )

    def persist_events(self, session_id: str) -> Path:
        """Persist current events to disk.

        Args:
            session_id: Session identifier for the log file.

        Returns:
            Path to the persisted log file.
        """
        log_file = self.log_dir / f"session_{session_id}.json"

        # Write to temp file first for crash safety
        temp_file = log_file.with_suffix(".tmp")
        data = {
            "session_id": session_id,
            "events": [event.to_dict() for event in self._current_events],
        }

        with open(temp_file, "w") as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        temp_file.rename(log_file)

        # Clear current events after persisting
        self._current_events.clear()

        return log_file

    def get_events(
        self, session_id: str | None = None, limit: int = 100
    ) -> list[HealingEvent]:
        """Retrieve logged events.

        Args:
            session_id: Specific session to retrieve (None for current events).
            limit: Maximum number of events to return.

        Returns:
            List of healing events.
        """
        if session_id:
            log_file = self.log_dir / f"session_{session_id}.json"
            if not log_file.exists():
                return []

            with open(log_file) as f:
                data = json.load(f)

            return data.get("events", [])[:limit]

        return self._current_events[:limit]


class EscalationManager:
    """Manager for escalating unhealable conditions.

    This class handles the escalation of issues that cannot be automatically
    healed, including notification generation and tracking.
    """

    def __init__(self, config: HealingConfig) -> None:
        """Initialize the escalation manager.

        Args:
            config: Healing configuration.
        """
        self.config = config
        self._escalations: dict[str, dict[str, Any]] = {}

    def should_escalate(
        self,
        healing_attempts: int,
        diagnostic_result: DiagnosticResult | None = None,
    ) -> bool:
        """Determine if an issue should be escalated.

        Args:
            healing_attempts: Number of healing attempts already made.
            diagnostic_result: Diagnostic result to assess.

        Returns:
            True if escalation is warranted.
        """
        # Escalate if max attempts reached
        if healing_attempts >= self.config.max_healing_attempts:
            return True

        # Escalate if diagnostic suggests escalation
        if diagnostic_result and diagnostic_result.requires_escalation:
            return True

        return False

    def create_escalation(
        self,
        session_id: str,
        diagnostic_result: DiagnosticResult,
        health_assessment: HealthAssessment,
    ) -> dict[str, Any]:
        """Create an escalation record.

        Args:
            session_id: Session identifier.
            diagnostic_result: Diagnostic result.
            health_assessment: Current health assessment.

        Returns:
            Escalation record.
        """
        escalation = {
            "escalation_id": f"escal_{session_id}",
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "severity": health_assessment.status.value,
            "summary": self._generate_summary(diagnostic_result, health_assessment),
            "root_cause": diagnostic_result.primary_cause.to_dict() if diagnostic_result.primary_cause else None,
            "root_causes": [rc.to_dict() for rc in diagnostic_result.root_causes],
            "healing_plan": diagnostic_result.healing_plan,
            "requires_escalation": diagnostic_result.requires_escalation,
            "recommended_actions": self._generate_recommendations(diagnostic_result),
            "status": "open",
        }

        self._escalations[session_id] = escalation
        logger.warning(f"Escalation created: {escalation['escalation_id']}")

        return escalation

    def _generate_summary(
        self,
        diagnostic_result: DiagnosticResult,
        health_assessment: HealthAssessment,
    ) -> str:
        """Generate a summary for escalation.

        Args:
            diagnostic_result: Diagnostic result.
            health_assessment: Health assessment.

        Returns:
            Summary string.
        """
        summary = f"Workflow health is {health_assessment.status.value}. "

        if diagnostic_result.primary_cause:
            summary += f"Root cause: {diagnostic_result.primary_cause.description}. "

        if diagnostic_result.root_causes:
            summary += f"Found {len(diagnostic_result.root_causes)} potential cause(s). "

        if diagnostic_result.healing_plan:
            strategy = diagnostic_result.healing_plan.get("strategy")
            if strategy:
                summary += f"Suggested strategy: {strategy}. "

        summary += "Requires human intervention."

        return summary

    def _generate_recommendations(
        self, diagnostic_result: DiagnosticResult
    ) -> list[str]:
        """Generate recommendations for escalation.

        Args:
            diagnostic_result: Diagnostic result.

        Returns:
            List of recommended actions.
        """
        recommendations = []

        if diagnostic_result.primary_cause:
            cause = diagnostic_result.primary_cause
            recommendations.append(f"Investigate {cause.category.value} issue: {cause.description}")

        if diagnostic_result.root_causes:
            for cause in diagnostic_result.root_causes:
                recommendations.append(f"Review {cause.category.value}: {cause.description}")

        recommendations.append("Review healing history and logs")
        recommendations.append("Consider adjusting healing thresholds or configuration")

        if diagnostic_result.degradation_signals:
            recommendations.append(f"Address {len(diagnostic_result.degradation_signals)} degradation signal(s)")

        return recommendations

    def get_escalation(self, session_id: str) -> dict[str, Any] | None:
        """Get escalation record for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Escalation record if found.
        """
        return self._escalations.get(session_id)


class HealingOrchestrator:
    """Closed-loop orchestrator for self-healing workflows.

    This class coordinates the complete self-healing workflow:
    1. Monitor for workflow degradation
    2. Diagnose root causes
    3. Execute healing actions
    4. Verify healing results
    5. Rollback on failure or escalate if unhealable

    The orchestrator maintains transparency through comprehensive logging
    and provides escalation paths for conditions that cannot be automatically healed.
    """

    def __init__(
        self,
        config: HealingConfig,
        monitor: WorkflowHealthMonitor,
        analyzer: RootCauseAnalyzer,
        selector: StrategySelector,
        registry: ActionRegistry,
        rollback_manager: RollbackManager,
        recovery_learner: RecoveryLearner | None = None,
    ) -> None:
        """Initialize the healing orchestrator.

        Args:
            config: Healing configuration.
            monitor: Health monitoring system.
            analyzer: Root cause analyzer.
            selector: Strategy selector.
            registry: Action registry.
            rollback_manager: Rollback manager.
            recovery_learner: Recovery learner for recording attempts (optional).
        """
        self.config = config
        self.monitor = monitor
        self.analyzer = analyzer
        self.selector = selector
        self.registry = registry
        self.rollback_manager = rollback_manager

        self.state = OrchestratorState.IDLE
        self._current_session: HealingSession | None = None
        self._session_counter = 0

        # Initialize event logger
        log_dir = self.config.project_root / ".auto-claude" / "healing" / "logs"
        self.event_logger = HealingEventLogger(log_dir)

        # Initialize escalation manager
        self.escalation_manager = EscalationManager(config)

        # Initialize recovery learner
        if recovery_learner is None:
            learning_path = config.project_root / ".autoflow" / "recovery_learning.json"
            recovery_learner = RecoveryLearner(learning_path=learning_path)
        self.recovery_learner = recovery_learner

    async def run_healing_cycle(
        self, trigger_assessment: HealthAssessment | None = None
    ) -> HealingOutcome:
        """Run a complete healing cycle.

        Args:
            trigger_assessment: Health assessment that triggered healing (optional).

        Returns:
            Final outcome of the healing cycle.
        """
        # Create new session
        self._current_session = self._create_session(trigger_assessment)
        session_id = self._current_session.session_id

        # Log cycle start
        self._log_event(
            event_type="healing_cycle_started",
            severity="info",
            description="Healing cycle initiated",
        )

        try:
            # Phase 1: Monitoring
            assessment = await self._monitor_phase(trigger_assessment)
            if assessment.status == WorkflowHealthStatus.HEALTHY:
                return self._complete_session(HealingOutcome.SKIPPED)

            # Phase 2: Diagnosis
            diagnostic_result = await self._diagnosis_phase(assessment)
            if not diagnostic_result or not diagnostic_result.root_causes:
                return self._complete_session(HealingOutcome.ESCALATED)

            # Phase 3: Healing
            outcome = await self._healing_phase(diagnostic_result, assessment)

            return self._complete_session(outcome)

        except Exception as e:
            logger.exception(f"Error during healing cycle: {e}")
            self._log_event(
                event_type="healing_cycle_error",
                severity="critical",
                description=f"Healing cycle error: {e}",
            )
            return self._complete_session(HealingOutcome.FAILED)

        finally:
            # Persist events
            self.event_logger.persist_events(session_id)

    async def _monitor_phase(
        self, trigger_assessment: HealthAssessment | None
    ) -> HealthAssessment:
        """Execute the monitoring phase.

        Args:
            trigger_assessment: Initial assessment (if available).

        Returns:
            Current health assessment.
        """
        # Create session if one doesn't exist (for direct testing)
        if not self._current_session:
            self._current_session = self._create_session(trigger_assessment)

        self.state = OrchestratorState.MONITORING
        self._log_event(
            event_type="monitoring_started",
            severity="info",
            description="Starting health monitoring phase",
        )

        if trigger_assessment:
            assessment = trigger_assessment
        else:
            assessment = self.monitor.assess_health()

        logger.info(f"Health assessment: {assessment.status.value}")
        self._log_event(
            event_type="health_assessment",
            severity="info" if assessment.status == WorkflowHealthStatus.HEALTHY else "warning",
            description=f"Health status: {assessment.status.value}",
            metadata={
                "metrics": {k: v.value for k, v in assessment.metrics.items()},
                "violations": assessment.violations,
            },
        )

        return assessment

    async def _diagnosis_phase(
        self, assessment: HealthAssessment
    ) -> DiagnosticResult | None:
        """Execute the diagnosis phase.

        Args:
            assessment: Health assessment to diagnose.

        Returns:
            Diagnostic result.
        """
        self.state = OrchestratorState.DIAGNOSING
        self._log_event(
            event_type="diagnosis_started",
            severity="warning",
            description="Starting root cause analysis",
        )

        diagnostic_result = await self.analyzer.analyze_failure(assessment)

        self._log_event(
            event_type="diagnosis_completed",
            severity="warning",
            description=f"Root cause identified: {diagnostic_result.primary_cause.description if diagnostic_result.primary_cause else 'Unknown'}",
            diagnostic_result=diagnostic_result,
            metadata={
                "num_root_causes": len(diagnostic_result.root_causes),
                "requires_escalation": diagnostic_result.requires_escalation,
                "analysis_duration": diagnostic_result.analysis_duration,
            },
        )

        return diagnostic_result

    async def _healing_phase(
        self, diagnostic_result: DiagnosticResult, assessment: HealthAssessment
    ) -> HealingOutcome:
        """Execute the healing phase.

        Args:
            diagnostic_result: Diagnostic result.
            assessment: Current health assessment.

        Returns:
            Healing outcome.
        """
        self.state = OrchestratorState.HEALING

        # Generate healing plan
        healing_plan = self.selector.select_healing_strategy(diagnostic_result)

        # Check if no healing plan could be created (escalation needed)
        if not healing_plan:
            return await self._escalate(diagnostic_result, assessment)

        self._log_event(
            event_type="healing_plan_created",
            severity="warning",
            description=f"Healing plan created with {len(healing_plan.execution_steps)} steps",
            metadata={
                "strategy": healing_plan.selected_strategy.value,
                "estimated_duration": healing_plan.estimated_duration,
                "fallback_strategies": [s.value for s in healing_plan.fallback_strategies],
            },
        )

        # Check if we should escalate immediately
        if self.escalation_manager.should_escalate(0, diagnostic_result):
            return await self._escalate(diagnostic_result, assessment)

        # Execute healing actions
        for action in healing_plan.execution_steps:
            # Skip string steps (descriptions only)
            if isinstance(action, str):
                continue

            outcome = await self._execute_action(action, diagnostic_result)

            if outcome != HealingOutcome.HEALED:
                return outcome

        return HealingOutcome.HEALED

    async def _execute_action(
        self, action: HealingAction, diagnostic_result: DiagnosticResult
    ) -> HealingOutcome:
        """Execute a single healing action.

        Args:
            action: Action to execute.
            diagnostic_result: Associated diagnostic result.

        Returns:
            Action outcome.
        """
        # Create session if one doesn't exist (for direct testing)
        if not self._current_session:
            self._current_session = self._create_session(None)

        self._log_event(
            event_type="action_started",
            severity="warning",
            description=f"Executing action: {action.action_type.value}",
            healing_action=action,
        )

        self._current_session.healing_attempts += 1
        start_time = datetime.now()
        action_result = await self.registry.execute_action(action)
        execution_time = (datetime.now() - start_time).total_seconds()

        self._log_event(
            event_type="action_completed",
            severity="info" if action_result.success else "error",
            description=f"Action {action.action_type.value}: {action_result.message}",
            healing_action=action,
            action_result=action_result,
        )

        if not action_result.success:
            # Record failed recovery attempt
            self._record_recovery_attempt(
                action=action,
                action_result=action_result,
                diagnostic_result=diagnostic_result,
                outcome=HealingOutcome.FAILED,
                execution_time=execution_time,
            )

            # Rollback on failure
            if action_result.can_rollback:
                return await self._rollback_action(action, action_result)

            # Escalate if cannot heal
            if self.escalation_manager.should_escalate(
                self._current_session.healing_attempts, diagnostic_result
            ):
                return await self._escalate(diagnostic_result, None)

            return HealingOutcome.FAILED

        # Verify action
        outcome = await self._verify_action(action, action_result)

        # Record recovery attempt with final outcome
        self._record_recovery_attempt(
            action=action,
            action_result=action_result,
            diagnostic_result=diagnostic_result,
            outcome=outcome,
            execution_time=execution_time,
        )

        return outcome

    async def _verify_action(
        self, action: HealingAction, action_result: ActionResult
    ) -> HealingOutcome:
        """Verify the result of a healing action.

        Args:
            action: Action that was executed.
            action_result: Result of the action.

        Returns:
            Verification outcome.
        """
        self.state = OrchestratorState.VERIFYING

        self._log_event(
            event_type="verification_started",
            severity="info",
            description="Verifying healing action",
            healing_action=action,
            action_result=action_result,
        )

        # Reassess health
        new_assessment = self.monitor.assess_health()

        if new_assessment.status == WorkflowHealthStatus.HEALTHY:
            self._log_event(
                event_type="verification_passed",
                severity="info",
                description="Healing verified - workflow is healthy",
            )
            return HealingOutcome.HEALED

        # Still degraded
        self._log_event(
            event_type="verification_failed",
            severity="warning",
            description="Healing action did not resolve degradation",
            metadata={
                "current_status": new_assessment.status.value,
            },
        )

        # Check if we should escalate
        if self.escalation_manager.should_escalate(self._current_session.healing_attempts):
            return await self._escalate(None, new_assessment)

        return HealingOutcome.FAILED

    async def _rollback_action(
        self, action: HealingAction, action_result: ActionResult
    ) -> HealingOutcome:
        """Rollback a failed healing action.

        Args:
            action: Action to rollback.
            action_result: Result that triggered rollback.

        Returns:
            Rollback outcome.
        """
        self._log_event(
            event_type="rollback_started",
            severity="error",
            description=f"Rolling back action: {action.action_type.value}",
            healing_action=action,
            action_result=action_result,
        )

        start_time = datetime.now()
        try:
            await self.rollback_manager.rollback_to_checkpoint(action.id)
            execution_time = (datetime.now() - start_time).total_seconds()
            self._log_event(
                event_type="rollback_completed",
                severity="info",
                description="Rollback completed successfully",
            )

            # Record the rollback as a failed recovery attempt
            self._record_recovery_attempt(
                action=action,
                action_result=action_result,
                diagnostic_result=None,
                outcome=HealingOutcome.ROLLED_BACK,
                execution_time=execution_time,
            )

            return HealingOutcome.ROLLED_BACK
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.exception(f"Rollback failed: {e}")
            self._log_event(
                event_type="rollback_failed",
                severity="critical",
                description=f"Rollback failed: {e}",
            )

            # Record the failed rollback
            self._record_recovery_attempt(
                action=action,
                action_result=action_result,
                diagnostic_result=None,
                outcome=HealingOutcome.FAILED,
                execution_time=execution_time,
            )

            return HealingOutcome.FAILED

    async def _escalate(
        self, diagnostic_result: DiagnosticResult | None, assessment: HealthAssessment | None
    ) -> HealingOutcome:
        """Escalate an unhealable condition.

        Args:
            diagnostic_result: Diagnostic result (if available).
            assessment: Health assessment (if available).

        Returns:
            Escalation outcome.
        """
        self.state = OrchestratorState.ESCALATING

        if not self._current_session:
            return HealingOutcome.ESCALATED

        # Create default diagnostic result if not provided
        if not diagnostic_result:
            from autoflow.healing.diagnostic import RootCause, FailureCategory, ConfidenceLevel
            default_cause = RootCause(
                category=FailureCategory.UNKNOWN,
                description="Unable to diagnose - escalating for manual investigation",
                evidence=[],
                confidence=ConfidenceLevel.LOW,
                affected_components=[],
                related_metrics=[],
                suggested_strategies=[],
            )
            diagnostic_result = DiagnosticResult(
                timestamp=datetime.now(),
                health_status=WorkflowHealthStatus.CRITICAL,
                root_causes=[default_cause],
                primary_cause=default_cause,
                degradation_signals=[],
                metadata={},
                healing_plan={},
                requires_escalation=True,
                analysis_duration=0.0,
            )

        # Create default assessment if not provided
        if not assessment:
            assessment = HealthAssessment(
                status=WorkflowHealthStatus.CRITICAL,
                timestamp=datetime.now(),
                metrics={},
                violations=[],
                recommendations=[],
            )

        escalation = self.escalation_manager.create_escalation(
            self._current_session.session_id,
            diagnostic_result,
            assessment,
        )

        self._log_event(
            event_type="escalation_created",
            severity="critical",
            description=f"Issue escalated: {escalation['escalation_id']}",
            metadata=escalation,
        )

        # Record the escalation as a recovery attempt
        # Note: We don't have a specific action here, so we create a placeholder
        from autoflow.healing.actions import HealingAction, ActionType
        escalation_action = HealingAction(
            action_id=f"escalation_{self._current_session.session_id}",
            action_type=ActionType.ESCALATE,
            description="Escalation to human operator",
            parameters={"escalation_id": escalation["escalation_id"]},
        )

        # Create a placeholder action result
        from autoflow.healing.actions import ActionResult
        escalation_result = ActionResult(
            success=False,
            message="Issue escalated to human operator",
            changes_made=[],
            can_rollback=False,
            error=None,
        )

        self._record_recovery_attempt(
            action=escalation_action,
            action_result=escalation_result,
            diagnostic_result=diagnostic_result,
            outcome=HealingOutcome.ESCALATED,
            execution_time=0.0,
        )

        return HealingOutcome.ESCALATED

    def _create_session(
        self, initial_assessment: HealthAssessment | None
    ) -> HealingSession:
        """Create a new healing session.

        Args:
            initial_assessment: Initial health assessment.

        Returns:
            New healing session.
        """
        self._session_counter += 1
        return HealingSession(
            session_id=f"session_{self._session_counter}_{int(datetime.now().timestamp())}",
            start_time=datetime.now(),
            initial_assessment=initial_assessment,
        )

    def _complete_session(self, outcome: HealingOutcome) -> HealingOutcome:
        """Complete the current healing session.

        Args:
            outcome: Final outcome of the session.

        Returns:
            The outcome.
        """
        if self._current_session:
            self._current_session.end_time = datetime.now()
            self._current_session.final_outcome = outcome

            self._log_event(
                event_type="session_completed",
                severity="info",
                description=f"Healing session completed: {outcome.value}",
                metadata={
                    "outcome": outcome.value,
                    "healing_attempts": self._current_session.healing_attempts,
                    "duration_seconds": (
                        self._current_session.end_time - self._current_session.start_time
                    ).total_seconds(),
                },
            )

        self.state = OrchestratorState.IDLE
        return outcome

    def _log_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        diagnostic_result: DiagnosticResult | None = None,
        healing_action: Any = None,
        action_result: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a healing event.

        Args:
            event_type: Type of event.
            severity: Severity level.
            description: Event description.
            diagnostic_result: Associated diagnostic result.
            healing_action: Associated healing action.
            action_result: Associated action result.
            metadata: Additional metadata.
        """
        if not self._current_session:
            return

        event = HealingEvent(
            event_id=f"{self._current_session.session_id}_{len(self._current_session.events)}",
            timestamp=datetime.now(),
            orchestrator_state=self.state,
            event_type=event_type,
            severity=severity,
            health_status=self._current_session.initial_assessment.status
            if self._current_session.initial_assessment
            else WorkflowHealthStatus.HEALTHY,
            description=description,
            metadata=metadata or {},
            diagnostic_result=diagnostic_result,
            healing_action=healing_action,
            action_result=action_result,
        )

        self.event_logger.log_event(event)
        self._current_session.events.append(event)

    def get_current_session(self) -> HealingSession | None:
        """Get the current healing session.

        Returns:
            Current session if exists.
        """
        return self._current_session

    def get_state(self) -> OrchestratorState:
        """Get the current orchestrator state.

        Returns:
            Current state.
        """
        return self.state

    def _map_healing_outcome(self, outcome: HealingOutcome) -> RecoveryOutcome:
        """Map healing outcome to recovery outcome.

        Args:
            outcome: Healing outcome from orchestrator.

        Returns:
            Recovery outcome for learning system.
        """
        mapping = {
            HealingOutcome.HEALED: RecoveryOutcome.SUCCESS,
            HealingOutcome.FAILED: RecoveryOutcome.FAILED,
            HealingOutcome.ROLLED_BACK: RecoveryOutcome.FAILED,
            HealingOutcome.ESCALATED: RecoveryOutcome.ESCALATED,
            HealingOutcome.SKIPPED: RecoveryOutcome.FAILED,
        }
        return mapping.get(outcome, RecoveryOutcome.FAILED)

    def _generate_pattern_id(self, diagnostic_result: DiagnosticResult | None) -> str:
        """Generate pattern ID from diagnostic result.

        Args:
            diagnostic_result: Diagnostic result to analyze.

        Returns:
            Pattern ID string.
        """
        if not diagnostic_result or not diagnostic_result.primary_cause:
            return "unknown-error"

        cause = diagnostic_result.primary_cause
        category = cause.category.value if cause.category else "unknown"
        description = cause.description.lower() if cause.description else ""

        # Create simple pattern ID from category and description
        # Remove special characters and normalize spaces
        import re
        normalized_desc = re.sub(r'[^\w\s-]', '', description)
        normalized_desc = re.sub(r'[-\s]+', '-', normalized_desc.strip())
        normalized_desc = normalized_desc[:50]  # Limit length

        return f"{category}-{normalized_desc}" if normalized_desc else category

    def _record_recovery_attempt(
        self,
        action: HealingAction,
        action_result: ActionResult,
        diagnostic_result: DiagnosticResult | None = None,
        outcome: HealingOutcome = HealingOutcome.FAILED,
        execution_time: float = 0.0,
    ) -> None:
        """Record a recovery attempt for learning.

        Args:
            action: The healing action that was executed.
            action_result: Result of the action execution.
            diagnostic_result: Associated diagnostic result.
            outcome: Final outcome of the healing attempt.
            execution_time: Time taken to execute the action.
        """
        try:
            # Generate pattern ID from diagnostic result
            pattern_id = self._generate_pattern_id(diagnostic_result)

            # Map healing outcome to recovery outcome
            recovery_outcome = self._map_healing_outcome(outcome)

            # Extract metadata for learning
            metadata = {
                "session_id": self._current_session.session_id if self._current_session else "",
                "action_id": action.action_id,
                "error_category": diagnostic_result.primary_cause.category.value
                if diagnostic_result and diagnostic_result.primary_cause
                else "unknown",
                "error_signature": diagnostic_result.primary_cause.description
                if diagnostic_result and diagnostic_result.primary_cause
                else "",
                "health_status": self._current_session.initial_assessment.status.value
                if self._current_session and self._current_session.initial_assessment
                else "unknown",
            }

            # Record the attempt
            self.recovery_learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used=action.action_type.value,
                action_type=action.action_type.value,
                parameters=action.parameters,
                outcome=recovery_outcome,
                success=(outcome == HealingOutcome.HEALED),
                execution_time=execution_time,
                error=action_result.error if not action_result.success else None,
                changes_made=action_result.changes_made,
                verification_passed=(outcome == HealingOutcome.HEALED),
                outcome_details=action_result.message,
                metadata=metadata,
            )
        except Exception as e:
            # Don't let recording errors interrupt healing flow
            logger.warning(f"Failed to record recovery attempt for learning: {e}")
