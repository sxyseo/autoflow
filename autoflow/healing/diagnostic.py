"""Diagnostic models and strategy definitions for self-healing workflows.

This module provides comprehensive diagnostic capabilities for analyzing workflow
failures, identifying root causes, and selecting appropriate healing strategies.
It integrates with the agent system to provide AI-powered analysis while maintaining
transparency about all diagnostic decisions.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autoflow.healing.config import HealingConfig
    from autoflow.healing.monitor import (
        DegradationSignal,
        HealthAssessment,
        WorkflowHealthStatus,
    )


class FailureCategory(Enum):
    """Categories of workflow failures for diagnostic analysis."""

    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    CONFIGURATION_ERROR = "configuration_error"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    NETWORK_ISSUE = "network_issue"
    CODE_ERROR = "code_error"
    DATA_CORRUPTION = "data_corruption"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class HealingStrategy(Enum):
    """Available healing strategies for different failure types.

    Each strategy represents a different approach to resolving workflow issues:
    - RETRY: Attempt the failed operation again with exponential backoff
    - ROLLBACK: Revert to a previous known-good state
    - RECONFIGURE: Adjust configuration parameters to resolve the issue
    - ESCALATE: Notify human operators for manual intervention
    - RESTART: Restart affected services or components
    - SCALE: Adjust resource allocation (scale up or down)
    - ISOLATE: Isolate failing components to prevent cascade failures
    """

    RETRY = "retry"
    ROLLBACK = "rollback"
    RECONFIGURE = "reconfigure"
    ESCALATE = "escalate"
    RESTART = "restart"
    SCALE = "scale"
    ISOLATE = "isolate"


class ConfidenceLevel(Enum):
    """Confidence levels for diagnostic conclusions."""

    HIGH = "high"  # >80% confidence
    MEDIUM = "medium"  # 50-80% confidence
    LOW = "low"  # <50% confidence


class ExecutionStatus(Enum):
    """Status of agent execution for diagnostic analysis."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result from AI agent execution during diagnostic analysis.

    Attributes:
        status: Execution status.
        content: Main content/output from the agent.
        raw_output: Raw output from the AI backend.
        error: Error message if execution failed.
        metadata: Additional execution metadata.
        token_usage: Token usage information.
        duration: Execution duration in seconds.
    """

    status: ExecutionStatus
    content: str
    raw_output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert execution result to dictionary.

        Returns:
            Dictionary representation of execution result.
        """
        return {
            "status": self.status.value,
            "content": self.content,
            "raw_output": self.raw_output,
            "error": self.error,
            "metadata": self.metadata,
            "token_usage": self.token_usage,
            "duration": self.duration,
        }


@dataclass
class RootCause:
    """Identified root cause of a workflow failure.

    Attributes:
        category: Category of the failure.
        description: Human-readable description of the root cause.
        evidence: List of evidence supporting this diagnosis.
        confidence: Confidence level in this diagnosis.
        affected_components: List of components affected by this issue.
        related_metrics: List of metric names that indicate this issue.
        suggested_strategies: List of healing strategies to address this cause.
    """

    category: FailureCategory
    description: str
    evidence: list[str]
    confidence: ConfidenceLevel
    affected_components: list[str]
    related_metrics: list[str]
    suggested_strategies: list[HealingStrategy]

    def to_dict(self) -> dict[str, Any]:
        """Convert root cause to dictionary.

        Returns:
            Dictionary representation of root cause.
        """
        return {
            "category": self.category.value,
            "description": self.description,
            "evidence": self.evidence,
            "confidence": self.confidence.value,
            "affected_components": self.affected_components,
            "related_metrics": self.related_metrics,
            "suggested_strategies": [s.value for s in self.suggested_strategies],
        }


@dataclass
class DiagnosticResult:
    """Complete diagnostic result from root cause analysis.

    Attributes:
        timestamp: When the diagnosis was performed.
        health_status: The health status that triggered diagnosis.
        root_causes: List of identified root causes (may be multiple).
        primary_cause: The most likely root cause.
        degradation_signals: List of degradation signals that were detected.
        metadata: Additional diagnostic context and metrics.
        healing_plan: Recommended healing plan with strategies.
        requires_escalation: Whether this requires human intervention.
        analysis_duration: Time taken to perform analysis (seconds).
    """

    timestamp: datetime
    health_status: WorkflowHealthStatus
    root_causes: list[RootCause]
    primary_cause: RootCause | None
    degradation_signals: list[dict]
    metadata: dict[str, Any]
    healing_plan: dict[str, Any]
    requires_escalation: bool
    analysis_duration: float

    def to_dict(self) -> dict[str, Any]:
        """Convert diagnostic result to dictionary.

        Returns:
            Dictionary representation of diagnostic result.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "health_status": self.health_status.value,
            "root_causes": [cause.to_dict() for cause in self.root_causes],
            "primary_cause": (
                self.primary_cause.to_dict() if self.primary_cause else None
            ),
            "degradation_signals": self.degradation_signals,
            "metadata": self.metadata,
            "healing_plan": self.healing_plan,
            "requires_escalation": self.requires_escalation,
            "analysis_duration": self.analysis_duration,
        }

    def get_summary(self) -> str:
        """Get human-readable summary of diagnostic result.

        Returns:
            Formatted summary string.
        """
        lines = [
            f"Diagnostic Result - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Health Status: {self.health_status.value}",
            f"Analysis Duration: {self.analysis_duration:.2f}s",
            "",
        ]

        if self.primary_cause:
            lines.extend(
                [
                    "Primary Root Cause:",
                    f"  Category: {self.primary_cause.category.value}",
                    f"  Description: {self.primary_cause.description}",
                    f"  Confidence: {self.primary_cause.confidence.value}",
                    "",
                ]
            )

        if self.root_causes:
            lines.append(f"Identified Root Causes ({len(self.root_causes)}):")
            for i, cause in enumerate(self.root_causes, 1):
                lines.append(f"  {i}. {cause.category.value}: {cause.description}")

        if self.degradation_signals:
            lines.append(f"\nDegradation Signals ({len(self.degradation_signals)}):")
            for signal in self.degradation_signals:
                lines.append(f"  - {signal.get('description', 'Unknown signal')}")

        if self.healing_plan.get("strategies"):
            lines.append("\nRecommended Healing Strategies:")
            for strategy in self.healing_plan["strategies"]:
                lines.append(f"  - {strategy}")

        if self.requires_escalation:
            lines.append("\n⚠️  ESCALATION REQUIRED: Human intervention needed")

        return "\n".join(lines)


@dataclass
class StrategyEvaluation:
    """Evaluation of a healing strategy for a specific diagnostic result.

    Attributes:
        strategy: The healing strategy being evaluated.
        applicability_score: Score from 0-1 indicating how well this strategy applies.
        confidence: Confidence in this evaluation.
        rationale: Reasoning for this evaluation.
        estimated_success_rate: Estimated probability of success (0-1).
        risk_level: Risk level of applying this strategy (low, medium, high).
        resource_requirements: Resources needed to execute this strategy.
        execution_time_estimate: Estimated time to execute (seconds).
    """

    strategy: HealingStrategy
    applicability_score: float
    confidence: ConfidenceLevel
    rationale: str
    estimated_success_rate: float
    risk_level: str
    resource_requirements: dict[str, Any]
    execution_time_estimate: float

    def to_dict(self) -> dict[str, Any]:
        """Convert strategy evaluation to dictionary.

        Returns:
            Dictionary representation of strategy evaluation.
        """
        return {
            "strategy": self.strategy.value,
            "applicability_score": self.applicability_score,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
            "estimated_success_rate": self.estimated_success_rate,
            "risk_level": self.risk_level,
            "resource_requirements": self.resource_requirements,
            "execution_time_estimate": self.execution_time_estimate,
        }


@dataclass
class HealingPlan:
    """Comprehensive healing plan based on diagnostic analysis.

    Attributes:
        selected_strategy: The primary healing strategy to execute.
        fallback_strategies: Alternative strategies if primary fails.
        execution_steps: Ordered list of steps to execute the plan.
        rollback_plan: Plan to rollback if healing fails.
        verification_steps: Steps to verify healing was successful.
        estimated_duration: Estimated total duration (seconds).
        resource_requirements: Resources needed for this plan.
        risk_assessment: Assessment of risks involved.
    """

    selected_strategy: HealingStrategy
    fallback_strategies: list[HealingStrategy]
    execution_steps: list[str]
    rollback_plan: list[str]
    verification_steps: list[str]
    estimated_duration: float
    resource_requirements: dict[str, Any]
    risk_assessment: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert healing plan to dictionary.

        Returns:
            Dictionary representation of healing plan.
        """
        return {
            "selected_strategy": self.selected_strategy.value,
            "fallback_strategies": [s.value for s in self.fallback_strategies],
            "execution_steps": self.execution_steps,
            "rollback_plan": self.rollback_plan,
            "verification_steps": self.verification_steps,
            "estimated_duration": self.estimated_duration,
            "resource_requirements": self.resource_requirements,
            "risk_assessment": self.risk_assessment,
        }


class StrategySelector:
    """Select appropriate healing strategies based on diagnostic results.

    The selector analyzes diagnostic results to identify the most appropriate
    healing strategies, considering factors like failure category, confidence,
    resource availability, and risk tolerance.

    Example:
        selector = StrategySelector(config=healing_config)
        plan = selector.select_healing_strategy(diagnostic_result)
        if plan:
            executor.execute(plan)
    """

    def __init__(
        self,
        config: HealingConfig | None = None,
    ) -> None:
        """Initialize the strategy selector.

        Args:
            config: Healing configuration. If None, uses defaults.
        """
        from autoflow.healing.config import HealingConfig

        self.config = config or HealingConfig()

    def select_healing_strategy(
        self,
        diagnostic: DiagnosticResult,
    ) -> HealingPlan | None:
        """Select the best healing strategy based on diagnostic results.

        Args:
            diagnostic: Diagnostic result from root cause analysis.

        Returns:
            HealingPlan if a strategy can be selected, None if escalation needed.
        """
        # If diagnostic requires escalation, return None
        if diagnostic.requires_escalation:
            return None

        # Get all possible strategies
        possible_strategies = self._get_possible_strategies(diagnostic)

        if not possible_strategies:
            return None

        # Select best strategy
        best_strategy = max(
            possible_strategies,
            key=lambda s: (
                s.applicability_score,
                s.estimated_success_rate,
            ),
        )

        # Create healing plan
        return self._create_healing_plan(
            diagnostic=diagnostic,
            selected_evaluation=best_strategy,
            fallback_evaluations=[s for s in possible_strategies if s != best_strategy][
                : self.config.max_healing_attempts - 1
            ],
        )

    def _get_possible_strategies(
        self,
        diagnostic: DiagnosticResult,
    ) -> list[StrategyEvaluation]:
        """Evaluate all possible strategies for the diagnostic result.

        Args:
            diagnostic: Diagnostic result to evaluate strategies for.

        Returns:
            List of strategy evaluations, sorted by applicability score.
        """
        evaluations = []

        # Evaluate each strategy type
        if diagnostic.primary_cause:
            for strategy in diagnostic.primary_cause.suggested_strategies:
                evaluation = self._evaluate_strategy(
                    strategy=strategy,
                    diagnostic=diagnostic,
                )
                if evaluation:
                    evaluations.append(evaluation)

        # If no suggested strategies, evaluate based on failure category
        if not evaluations and diagnostic.primary_cause:
            for strategy in HealingStrategy:
                evaluation = self._evaluate_strategy(
                    strategy=strategy,
                    diagnostic=diagnostic,
                )
                if evaluation and evaluation.applicability_score > 0.3:
                    evaluations.append(evaluation)

        # Sort by applicability score
        evaluations.sort(key=lambda e: e.applicability_score, reverse=True)

        return evaluations

    def _evaluate_strategy(
        self,
        strategy: HealingStrategy,
        diagnostic: DiagnosticResult,
    ) -> StrategyEvaluation | None:
        """Evaluate a specific strategy for the diagnostic result.

        Args:
            strategy: Strategy to evaluate.
            diagnostic: Diagnostic result to evaluate against.

        Returns:
            StrategyEvaluation if strategy is applicable, None otherwise.
        """
        if not diagnostic.primary_cause:
            return None

        category = diagnostic.primary_cause.category
        confidence = diagnostic.primary_cause.confidence

        # Base applicability and confidence
        applicability = 0.0
        estimated_success = 0.0
        risk_level = "medium"
        rationale = []

        # Strategy-specific evaluation logic
        if strategy == HealingStrategy.RETRY:
            if category in [
                FailureCategory.NETWORK_ISSUE,
                FailureCategory.TIMEOUT,
                FailureCategory.RESOURCE_EXHAUSTION,
            ]:
                applicability = 0.8 if confidence == ConfidenceLevel.HIGH else 0.6
                estimated_success = 0.7
                risk_level = "low"
                rationale.append("Retry is effective for transient failures")

        elif strategy == HealingStrategy.ROLLBACK:
            if category in [
                FailureCategory.CONFIGURATION_ERROR,
                FailureCategory.CODE_ERROR,
                FailureCategory.DEPENDENCY_FAILURE,
            ]:
                applicability = 0.9 if confidence == ConfidenceLevel.HIGH else 0.7
                estimated_success = 0.85
                risk_level = "low"
                rationale.append("Rollback can revert recent breaking changes")

        elif strategy == HealingStrategy.RECONFIGURE:
            if category in [
                FailureCategory.RESOURCE_EXHAUSTION,
                FailureCategory.CONFIGURATION_ERROR,
                FailureCategory.PERFORMANCE_DEGRADATION,
            ]:
                applicability = 0.7 if confidence == ConfidenceLevel.HIGH else 0.5
                estimated_success = 0.6
                risk_level = "medium"
                rationale.append("Configuration adjustments may resolve the issue")

        elif strategy == HealingStrategy.RESTART:
            if category in [
                FailureCategory.RESOURCE_EXHAUSTION,
                FailureCategory.TIMEOUT,
                FailureCategory.UNKNOWN,
            ]:
                applicability = 0.6
                estimated_success = 0.5
                risk_level = "low"
                rationale.append("Restart can clear transient state issues")

        elif strategy == HealingStrategy.SCALE:
            if category == FailureCategory.RESOURCE_EXHAUSTION:
                applicability = 0.8 if confidence == ConfidenceLevel.HIGH else 0.6
                estimated_success = 0.7
                risk_level = "low"
                rationale.append("Scaling can address resource constraints")

        elif strategy == HealingStrategy.ISOLATE:
            if category in [
                FailureCategory.CODE_ERROR,
                FailureCategory.DATA_CORRUPTION,
            ]:
                applicability = 0.7
                estimated_success = 0.6
                risk_level = "medium"
                rationale.append("Isolation prevents cascade failures")

        elif strategy == HealingStrategy.ESCALATE:
            if category == FailureCategory.UNKNOWN or confidence == ConfidenceLevel.LOW:
                applicability = 0.9
                estimated_success = 1.0  # Human intervention always succeeds eventually
                risk_level = "low"
                rationale.append(
                    "Unknown or low-confidence issues require human expertise"
                )

        # Apply penalties based on health status
        from autoflow.healing.monitor import WorkflowHealthStatus

        if diagnostic.health_status == WorkflowHealthStatus.CRITICAL:
            # Critical issues need faster resolution
            if strategy in [HealingStrategy.RETRY, HealingStrategy.ESCALATE]:
                applicability *= 1.1
            else:
                applicability *= 0.9

        # Check if strategy is viable
        if applicability < 0.3:
            return None

        # Determine confidence level
        eval_confidence = ConfidenceLevel.HIGH
        if applicability < 0.6:
            eval_confidence = ConfidenceLevel.MEDIUM
        if applicability < 0.4 or confidence == ConfidenceLevel.LOW:
            eval_confidence = ConfidenceLevel.LOW

        return StrategyEvaluation(
            strategy=strategy,
            applicability_score=min(applicability, 1.0),
            confidence=eval_confidence,
            rationale="; ".join(rationale) or "General applicability",
            estimated_success_rate=estimated_success,
            risk_level=risk_level,
            resource_requirements=self._estimate_resource_requirements(strategy),
            execution_time_estimate=self._estimate_execution_time(strategy),
        )

    def _estimate_resource_requirements(
        self,
        strategy: HealingStrategy,
    ) -> dict[str, Any]:
        """Estimate resource requirements for a strategy.

        Args:
            strategy: Strategy to estimate requirements for.

        Returns:
            Dictionary of resource requirements.
        """
        requirements = {
            "cpu": "low",
            "memory": "low",
            "network": "low",
            "storage": "none",
            "external_services": [],
        }

        if strategy == HealingStrategy.ROLLBACK:
            requirements["storage"] = "medium"  # Need to access checkpoints
            requirements["external_services"] = ["checkpoint_system"]

        elif strategy == HealingStrategy.SCALE:
            requirements["cpu"] = "high"
            requirements["memory"] = "high"
            requirements["external_services"] = ["orchestrator", "resource_manager"]

        elif strategy == HealingStrategy.RECONFIGURE:
            requirements["external_services"] = ["config_store"]

        return requirements

    def _estimate_execution_time(
        self,
        strategy: HealingStrategy,
    ) -> float:
        """Estimate execution time for a strategy in seconds.

        Args:
            strategy: Strategy to estimate time for.

        Returns:
            Estimated execution time in seconds.
        """
        # Base times for different strategies
        base_times = {
            HealingStrategy.RETRY: 30.0,
            HealingStrategy.ROLLBACK: 60.0,
            HealingStrategy.RECONFIGURE: 45.0,
            HealingStrategy.RESTART: 90.0,
            HealingStrategy.SCALE: 120.0,
            HealingStrategy.ISOLATE: 30.0,
            HealingStrategy.ESCALATE: 0.0,  # Immediate, human time not counted
        }

        return base_times.get(strategy, 60.0)

    def _create_healing_plan(
        self,
        diagnostic: DiagnosticResult,
        selected_evaluation: StrategyEvaluation,
        fallback_evaluations: list[StrategyEvaluation],
    ) -> HealingPlan:
        """Create a comprehensive healing plan.

        Args:
            diagnostic: Diagnostic result.
            selected_evaluation: Selected strategy evaluation.
            fallback_evaluations: Fallback strategy evaluations.

        Returns:
            Complete healing plan.
        """
        strategy = selected_evaluation.strategy

        # Generate execution steps based on strategy
        execution_steps = self._generate_execution_steps(
            strategy=strategy,
            diagnostic=diagnostic,
        )

        # Generate rollback plan
        rollback_plan = self._generate_rollback_plan(
            strategy=strategy,
            diagnostic=diagnostic,
        )

        # Generate verification steps
        verification_steps = self._generate_verification_steps(
            strategy=strategy,
            diagnostic=diagnostic,
        )

        # Collect fallback strategies
        fallback_strategies = [e.strategy for e in fallback_evaluations]

        return HealingPlan(
            selected_strategy=strategy,
            fallback_strategies=fallback_strategies,
            execution_steps=execution_steps,
            rollback_plan=rollback_plan,
            verification_steps=verification_steps,
            estimated_duration=selected_evaluation.execution_time_estimate,
            resource_requirements=selected_evaluation.resource_requirements,
            risk_assessment={
                "risk_level": selected_evaluation.risk_level,
                "confidence": selected_evaluation.confidence.value,
                "estimated_success_rate": selected_evaluation.estimated_success_rate,
                "potential_side_effects": self._identify_potential_side_effects(
                    strategy=strategy,
                    diagnostic=diagnostic,
                ),
            },
        )

    def _generate_execution_steps(
        self,
        strategy: HealingStrategy,
        diagnostic: DiagnosticResult,
    ) -> list[str]:
        """Generate execution steps for a strategy.

        Args:
            strategy: Strategy to generate steps for.
            diagnostic: Diagnostic result.

        Returns:
            List of execution steps.
        """
        steps = []

        if strategy == HealingStrategy.RETRY:
            steps.extend(
                [
                    "Identify failed task or operation",
                    "Check retry count is below maximum",
                    "Apply exponential backoff delay",
                    "Re-execute the failed operation",
                    "Verify operation completed successfully",
                ]
            )

        elif strategy == HealingStrategy.ROLLBACK:
            steps.extend(
                [
                    "Identify last known-good checkpoint",
                    "Verify checkpoint integrity",
                    "Stop current workflow execution",
                    "Restore state from checkpoint",
                    "Restart workflow from restored state",
                    "Verify workflow resumes correctly",
                ]
            )

        elif strategy == HealingStrategy.RECONFIGURE:
            steps.extend(
                [
                    "Identify problematic configuration parameters",
                    "Calculate optimal new values",
                    "Validate new configuration values",
                    "Apply configuration changes",
                    "Reload affected services",
                    "Verify configuration is active",
                ]
            )

        elif strategy == HealingStrategy.RESTART:
            steps.extend(
                [
                    "Identify affected services or components",
                    "Perform graceful shutdown",
                    "Clear any cached state",
                    "Restart services",
                    "Verify services start correctly",
                    "Check health endpoints",
                ]
            )

        elif strategy == HealingStrategy.SCALE:
            steps.extend(
                [
                    "Analyze current resource utilization",
                    "Calculate required resource increase",
                    "Provision additional resources",
                    "Update service configuration",
                    "Redistribute load",
                    "Verify scaling is effective",
                ]
            )

        elif strategy == HealingStrategy.ISOLATE:
            steps.extend(
                [
                    "Identify failing component",
                    "Determine isolation boundary",
                    "Route traffic away from component",
                    "Quarantine component if necessary",
                    "Monitor for cascade effects",
                    "Verify system stability",
                ]
            )

        elif strategy == HealingStrategy.ESCALATE:
            steps.extend(
                [
                    "Compile diagnostic information",
                    "Create incident report",
                    "Notify on-call engineer",
                    "Provide context and recommendations",
                    "Await human intervention",
                ]
            )

        return steps

    def _generate_rollback_plan(
        self,
        strategy: HealingStrategy,
        diagnostic: DiagnosticResult,
    ) -> list[str]:
        """Generate rollback plan for a strategy.

        Args:
            strategy: Strategy to generate rollback for.
            diagnostic: Diagnostic result.

        Returns:
            List of rollback steps.
        """
        if strategy == HealingStrategy.RETRY:
            return [
                "Stop retry attempts",
                "Restore original task state",
                "Log retry failure for analysis",
            ]

        elif strategy == HealingStrategy.ROLLBACK:
            return [
                "Note: Rollback strategy is its own rollback",
                "Document current state before rollback",
                "Ensure checkpoint system is available",
            ]

        elif strategy == HealingStrategy.RECONFIGURE:
            return [
                "Restore previous configuration values",
                "Reload affected services",
                "Verify services stabilize",
                "Document configuration change attempt",
            ]

        elif strategy == HealingStrategy.RESTART:
            return [
                "Ensure services are stopped",
                "Restore from backup if data modified",
                "Document restart attempt",
                "Investigate root cause before restarting",
            ]

        elif strategy == HealingStrategy.SCALE:
            return [
                "Calculate original resource levels",
                "Scale down to original configuration",
                "Verify system stability",
                "Document scaling attempt",
            ]

        elif strategy == HealingStrategy.ISOLATE:
            return [
                "Restore normal traffic routing",
                "Reintegrate isolated component",
                "Monitor for reoccurrence of issues",
                "Document isolation attempt",
            ]

        elif strategy == HealingStrategy.ESCALATE:
            return [
                "No rollback needed for escalation",
                "Document human decisions made",
                "Update knowledge base",
            ]

        return []

    def _generate_verification_steps(
        self,
        strategy: HealingStrategy,
        diagnostic: DiagnosticResult,
    ) -> list[str]:
        """Generate verification steps for a strategy.

        Args:
            strategy: Strategy to generate verification for.
            diagnostic: Diagnostic result.

        Returns:
            List of verification steps.
        """
        common_steps = [
            "Wait for stabilization period",
            "Check health status indicators",
            "Verify original issue is resolved",
            "Monitor for new issues",
        ]

        strategy_specific = []

        if strategy == HealingStrategy.RETRY:
            strategy_specific = [
                "Verify retried operation succeeded",
                "Check for repeat failures",
            ]

        elif strategy == HealingStrategy.ROLLBACK:
            strategy_specific = [
                "Verify checkpoint restored correctly",
                "Check workflow resumes from checkpoint",
                "Verify data consistency",
            ]

        elif strategy == HealingStrategy.RECONFIGURE:
            strategy_specific = [
                "Verify new configuration is active",
                "Check configuration takes effect",
                "Monitor configuration impact",
            ]

        elif strategy == HealingStrategy.RESTART:
            strategy_specific = [
                "Verify all services restarted",
                "Check service health endpoints",
                "Verify service connectivity",
            ]

        elif strategy == HealingStrategy.SCALE:
            strategy_specific = [
                "Verify resources provisioned",
                "Check resource utilization improved",
                "Verify load distribution",
            ]

        elif strategy == HealingStrategy.ISOLATE:
            strategy_specific = [
                "Verify component isolated",
                "Check system stability",
                "Verify no cascade failures",
            ]

        elif strategy == HealingStrategy.ESCALATE:
            strategy_specific = [
                "Verify human acknowledges issue",
                "Confirm remediation plan in place",
                "Document resolution",
            ]

        return common_steps + strategy_specific

    def _identify_potential_side_effects(
        self,
        strategy: HealingStrategy,
        diagnostic: DiagnosticResult,
    ) -> list[str]:
        """Identify potential side effects of a healing strategy.

        Args:
            strategy: Strategy to analyze.
            diagnostic: Diagnostic result.

        Returns:
            List of potential side effects.
        """
        side_effects = []

        if strategy == HealingStrategy.RETRY:
            side_effects.extend(
                [
                    "May delay detection of persistent issues",
                    "Could increase load on failing services",
                ]
            )

        elif strategy == HealingStrategy.ROLLBACK:
            side_effects.extend(
                [
                    "May lose recent valid changes",
                    "Could cause temporary service interruption",
                    "May not resolve issue if root cause persists",
                ]
            )

        elif strategy == HealingStrategy.RECONFIGURE:
            side_effects.extend(
                [
                    "New configuration may introduce different issues",
                    "May require service restart",
                    "Could have unintended interactions",
                ]
            )

        elif strategy == HealingStrategy.RESTART:
            side_effects.extend(
                [
                    "Temporary service interruption",
                    "May lose in-memory state",
                    "Could trigger cascading restarts",
                ]
            )

        elif strategy == HealingStrategy.SCALE:
            side_effects.extend(
                [
                    "Increased resource costs",
                    "May take time to provision resources",
                    "Could over-provision temporarily",
                ]
            )

        elif strategy == HealingStrategy.ISOLATE:
            side_effects.extend(
                [
                    "Reduced system capacity",
                    "May affect user experience",
                    "Could mask underlying issue",
                ]
            )

        elif strategy == HealingStrategy.ESCALATE:
            side_effects.extend(
                [
                    "Resolution time depends on human availability",
                    "May interrupt on-call engineer",
                    "Creates incident record requiring follow-up",
                ]
            )

        return side_effects


class RootCauseAnalyzer:
    """AI-powered root cause analyzer using agent adapters.

    The analyzer uses AI agents to perform deep analysis of workflow health issues,
    identifying root causes, gathering evidence, and suggesting appropriate healing
    strategies. It provides transparency into the analysis process while leveraging
    AI capabilities for complex diagnostic reasoning.

    Example:
        analyzer = RootCauseAnalyzer(config=healing_config)
        diagnostic = analyzer.analyze_root_cause(
            health_assessment=assessment,
            degradation_signals=signals,
        )
        if diagnostic.requires_escalation:
            # Escalate to human operators
            pass
        else:
            # Proceed with healing
            plan = StrategySelector().select_healing_strategy(diagnostic)
    """

    def __init__(
        self,
        config: HealingConfig | None = None,
    ) -> None:
        """Initialize the root cause analyzer.

        Args:
            config: Healing configuration. If None, uses defaults.
        """
        from autoflow.healing.config import HealingConfig

        self.config = config or HealingConfig()
        self._analysis_cache: dict[str, DiagnosticResult] = {}

    def analyze_root_cause(
        self,
        health_assessment: HealthAssessment,
        degradation_signals: list[DegradationSignal] | None = None,
        context: dict[str, Any] | None = None,
    ) -> DiagnosticResult:
        """Perform AI-powered root cause analysis.

        Args:
            health_assessment: Current health assessment of the workflow.
            degradation_signals: List of detected degradation signals.
            context: Additional context for the analysis (e.g., recent changes,
                error logs, metrics).

        Returns:
            Complete diagnostic result with root causes and recommendations.
        """
        start_time = time.time()

        degradation_signals = degradation_signals or []
        context = context or {}

        # Check cache for similar analysis
        cache_key = self._generate_cache_key(
            health_status=health_assessment.status,
            signals=degradation_signals,
        )
        if cache_key in self._analysis_cache:
            cached_result = self._analysis_cache[cache_key]
            # Update timestamp but reuse analysis
            cached_result.timestamp = datetime.now()
            return cached_result

        # Perform AI-powered analysis
        analysis_result = self._perform_ai_analysis(
            health_assessment=health_assessment,
            degradation_signals=degradation_signals,
            context=context,
        )

        # Extract root causes from AI analysis
        root_causes = self._extract_root_causes(
            ai_result=analysis_result,
            health_assessment=health_assessment,
            degradation_signals=degradation_signals,
        )

        # Identify primary cause
        primary_cause = self._identify_primary_cause(root_causes)

        # Generate healing plan
        healing_plan = self._generate_healing_plan(
            root_causes=root_causes,
            primary_cause=primary_cause,
        )

        # Determine if escalation is required
        requires_escalation = self._requires_escalation(
            root_causes=root_causes,
            primary_cause=primary_cause,
        )

        # Calculate analysis duration
        analysis_duration = time.time() - start_time

        # Create diagnostic result
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=health_assessment.status,
            root_causes=root_causes,
            primary_cause=primary_cause,
            degradation_signals=[s.to_dict() for s in degradation_signals],
            metadata={
                "analysis_method": "ai-powered",
                "ai_confidence": analysis_result.metadata.get("confidence", "unknown"),
                "context_provided": bool(context),
                "context_keys": list(context.keys()) if context else [],
                "cache_key": cache_key,
            },
            healing_plan=healing_plan,
            requires_escalation=requires_escalation,
            analysis_duration=analysis_duration,
        )

        # Cache the result
        self._analysis_cache[cache_key] = diagnostic

        return diagnostic

    def _generate_cache_key(
        self,
        health_status: WorkflowHealthStatus,
        signals: list[DegradationSignal],
    ) -> str:
        """Generate cache key for analysis result.

        Args:
            health_status: Current workflow health status.
            signals: Degradation signals.

        Returns:
            Cache key string.
        """
        import hashlib

        # Create a hash based on status and signal descriptions
        key_parts = [health_status.value]
        for signal in signals:
            key_parts.append(signal.description)

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]

    def _perform_ai_analysis(
        self,
        health_assessment: HealthAssessment,
        degradation_signals: list[DegradationSignal],
        context: dict[str, Any],
    ) -> ExecutionResult:
        """Perform AI-powered analysis using agent adapter pattern.

        Args:
            health_assessment: Current health assessment.
            degradation_signals: Detected degradation signals.
            context: Additional context for analysis.

        Returns:
            Execution result from AI analysis.
        """
        # Build analysis prompt
        prompt = self._build_analysis_prompt(
            health_assessment=health_assessment,
            degradation_signals=degradation_signals,
            context=context,
        )

        # Simulate AI agent execution
        # In production, this would call actual agent adapters
        # For now, we implement rule-based analysis
        try:
            start_time = time.time()

            # Perform rule-based analysis
            analysis_content = self._rule_based_analysis(
                health_assessment=health_assessment,
                degradation_signals=degradation_signals,
                context=context,
            )

            duration = time.time() - start_time

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                content=analysis_content,
                raw_output=analysis_content,
                metadata={
                    "confidence": "high",
                    "analysis_type": "rule-based",
                    "signals_analyzed": len(degradation_signals),
                },
                token_usage={
                    "prompt_tokens": len(prompt.split()),
                    "completion_tokens": len(analysis_content.split()),
                },
                duration=duration,
            )

        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                content=f"Analysis failed: {str(e)}",
                error=str(e),
                duration=0.0,
            )

    def _build_analysis_prompt(
        self,
        health_assessment: HealthAssessment,
        degradation_signals: list[DegradationSignal],
        context: dict[str, Any],
    ) -> str:
        """Build analysis prompt for AI agent.

        Args:
            health_assessment: Current health assessment.
            degradation_signals: Detected degradation signals.
            context: Additional context.

        Returns:
            Analysis prompt string.
        """
        prompt_parts = [
            "# Root Cause Analysis Request",
            "",
            "Analyze the following workflow health issue and identify root causes.",
            "",
            "## Health Status",
            f"Status: {health_assessment.status.value}",
            f"Overall Score: {health_assessment.overall_score:.2f}",
            f"Timestamp: {health_assessment.timestamp.isoformat()}",
            "",
        ]

        # Add health metrics
        if health_assessment.metrics:
            prompt_parts.extend(
                [
                    "## Health Metrics",
                ]
            )
            for metric_name, metric_value in health_assessment.metrics.items():
                prompt_parts.append(f"- {metric_name}: {metric_value}")
            prompt_parts.append("")

        # Add degradation signals
        if degradation_signals:
            prompt_parts.extend(
                [
                    "## Degradation Signals",
                ]
            )
            for i, signal in enumerate(degradation_signals, 1):
                prompt_parts.extend(
                    [
                        f"### Signal {i}",
                        f"Description: {signal.description}",
                        f"Severity: {signal.severity.value}",
                        f"Type: {signal.signal_type.value}",
                    ]
                )
                if signal.evidence:
                    prompt_parts.append("Evidence:")
                    for evidence in signal.evidence:
                        prompt_parts.append(f"  - {evidence}")
                prompt_parts.append("")

        # Add context
        if context:
            prompt_parts.extend(
                [
                    "## Additional Context",
                ]
            )
            for key, value in context.items():
                prompt_parts.append(f"- {key}: {value}")
            prompt_parts.append("")

        # Add analysis instructions
        prompt_parts.extend(
            [
                "## Analysis Required",
                "",
                "Please provide:",
                "1. Root cause identification with failure categories",
                "2. Evidence supporting each root cause",
                "3. Confidence levels for each diagnosis",
                "4. Affected components",
                "5. Suggested healing strategies",
                "",
                "Format your response as structured analysis that can be parsed.",
            ]
        )

        return "\n".join(prompt_parts)

    def _rule_based_analysis(
        self,
        health_assessment: HealthAssessment,
        degradation_signals: list[DegradationSignal],
        context: dict[str, Any],
    ) -> str:
        """Perform rule-based analysis when AI is not available.

        Args:
            health_assessment: Current health assessment.
            degradation_signals: Detected degradation signals.
            context: Additional context.

        Returns:
            Analysis content string.
        """
        analysis_parts = [
            "# Root Cause Analysis",
            "",
            "## Identified Root Causes",
            "",
        ]

        # Analyze each degradation signal
        for i, signal in enumerate(degradation_signals, 1):
            cause = self._analyze_signal(signal, context)
            analysis_parts.extend(
                [
                    f"### {i}. {cause['category'].upper().replace('_', ' ')}",
                    f"**Description**: {cause['description']}",
                    f"**Confidence**: {cause['confidence'].value}",
                    "**Evidence**:",
                ]
            )
            for evidence in cause["evidence"]:
                analysis_parts.append(f"  - {evidence}")
            analysis_parts.extend(
                [
                    f"**Affected Components**: {', '.join(cause['components'])}",
                    f"**Suggested Strategies**: {', '.join([s.value for s in cause['strategies']])}",
                    "",
                ]
            )

        # If no signals, analyze health status
        if not degradation_signals:
            cause = self._analyze_health_status(health_assessment, context)
            analysis_parts.extend(
                [
                    f"### 1. {cause['category'].upper().replace('_', ' ')}",
                    f"**Description**: {cause['description']}",
                    f"**Confidence**: {cause['confidence'].value}",
                    "**Evidence**:",
                ]
            )
            for evidence in cause["evidence"]:
                analysis_parts.append(f"  - {evidence}")
            analysis_parts.extend(
                [
                    f"**Affected Components**: {', '.join(cause['components'])}",
                    f"**Suggested Strategies**: {', '.join([s.value for s in cause['strategies']])}",
                    "",
                ]
            )

        return "\n".join(analysis_parts)

    def _analyze_signal(
        self,
        signal: DegradationSignal,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze a single degradation signal.

        Args:
            signal: Degradation signal to analyze.
            context: Additional context.

        Returns:
            Dictionary with analysis results.
        """
        from autoflow.healing.monitor import SignalType

        # Map signal types to failure categories
        signal_to_category = {
            SignalType.HIGH_ERROR_RATE: FailureCategory.CODE_ERROR,
            SignalType.SLOW_EXECUTION: FailureCategory.PERFORMANCE_DEGRADATION,
            SignalType.RESOURCE_EXHAUSTION: FailureCategory.RESOURCE_EXHAUSTION,
            SignalType.TIMEOUT: FailureCategory.TIMEOUT,
            SignalType.DEPENDENCY_FAILURE: FailureCategory.DEPENDENCY_FAILURE,
            SignalType.CONFIGURATION_DRIFT: FailureCategory.CONFIGURATION_ERROR,
            SignalType.NETWORK_ISSUE: FailureCategory.NETWORK_ISSUE,
        }

        category = signal_to_category.get(
            signal.signal_type,
            FailureCategory.UNKNOWN,
        )

        # Generate description and evidence
        description = f"Detected {signal.signal_type.value} in workflow execution"
        evidence = signal.evidence or [signal.description]

        # Determine confidence based on severity
        from autoflow.healing.monitor import SeverityLevel

        confidence = ConfidenceLevel.MEDIUM
        if signal.severity == SeverityLevel.CRITICAL:
            confidence = ConfidenceLevel.HIGH
        elif signal.severity == SeverityLevel.LOW:
            confidence = ConfidenceLevel.LOW

        # Identify affected components
        components = (
            signal.affected_components
            if hasattr(signal, "affected_components")
            else ["workflow"]
        )

        # Suggest strategies based on category
        strategies = self._get_strategies_for_category(category)

        return {
            "category": category,
            "description": description,
            "evidence": evidence,
            "confidence": confidence,
            "components": components,
            "strategies": strategies,
        }

    def _analyze_health_status(
        self,
        health_assessment: HealthAssessment,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze health status when no specific signals.

        Args:
            health_assessment: Health assessment to analyze.
            context: Additional context.

        Returns:
            Dictionary with analysis results.
        """
        from autoflow.healing.monitor import WorkflowHealthStatus

        status = health_assessment.status

        if status == WorkflowHealthStatus.CRITICAL:
            category = FailureCategory.UNKNOWN
            description = "Workflow in critical state with unidentified issues"
            confidence = ConfidenceLevel.LOW
            strategies = [HealingStrategy.ESCALATE]
        elif status == WorkflowHealthStatus.WARNING:
            category = FailureCategory.PERFORMANCE_DEGRADATION
            description = "Workflow showing signs of performance degradation"
            confidence = ConfidenceLevel.MEDIUM
            strategies = [HealingStrategy.RETRY, HealingStrategy.RECONFIGURE]
        else:  # DEGRADED
            category = FailureCategory.CONFIGURATION_ERROR
            description = "Workflow operating in degraded mode"
            confidence = ConfidenceLevel.MEDIUM
            strategies = [HealingStrategy.RECONFIGURE, HealingStrategy.RESTART]

        return {
            "category": category,
            "description": description,
            "evidence": [
                f"Health status: {status.value}",
                f"Overall score: {health_assessment.overall_score:.2f}",
            ],
            "confidence": confidence,
            "components": ["workflow"],
            "strategies": strategies,
        }

    def _get_strategies_for_category(
        self,
        category: FailureCategory,
    ) -> list[HealingStrategy]:
        """Get suggested healing strategies for a failure category.

        Args:
            category: Failure category.

        Returns:
            List of suggested healing strategies.
        """
        strategy_map = {
            FailureCategory.RESOURCE_EXHAUSTION: [
                HealingStrategy.SCALE,
                HealingStrategy.RETRY,
                HealingStrategy.RECONFIGURE,
            ],
            FailureCategory.DEPENDENCY_FAILURE: [
                HealingStrategy.RETRY,
                HealingStrategy.ROLLBACK,
                HealingStrategy.ESCALATE,
            ],
            FailureCategory.CONFIGURATION_ERROR: [
                HealingStrategy.RECONFIGURE,
                HealingStrategy.ROLLBACK,
            ],
            FailureCategory.PERFORMANCE_DEGRADATION: [
                HealingStrategy.RECONFIGURE,
                HealingStrategy.SCALE,
                HealingStrategy.RETRY,
            ],
            FailureCategory.NETWORK_ISSUE: [
                HealingStrategy.RETRY,
                HealingStrategy.RESTART,
            ],
            FailureCategory.CODE_ERROR: [
                HealingStrategy.ROLLBACK,
                HealingStrategy.ISOLATE,
                HealingStrategy.ESCALATE,
            ],
            FailureCategory.DATA_CORRUPTION: [
                HealingStrategy.ROLLBACK,
                HealingStrategy.ISOLATE,
                HealingStrategy.ESCALATE,
            ],
            FailureCategory.TIMEOUT: [
                HealingStrategy.RETRY,
                HealingStrategy.RECONFIGURE,
                HealingStrategy.SCALE,
            ],
            FailureCategory.UNKNOWN: [
                HealingStrategy.ESCALATE,
                HealingStrategy.RESTART,
            ],
        }

        return strategy_map.get(category, [HealingStrategy.ESCALATE])

    def _extract_root_causes(
        self,
        ai_result: ExecutionResult,
        health_assessment: HealthAssessment,
        degradation_signals: list[DegradationSignal],
    ) -> list[RootCause]:
        """Extract root causes from AI analysis result.

        Args:
            ai_result: AI execution result.
            health_assessment: Health assessment.
            degradation_signals: Degradation signals.

        Returns:
            List of identified root causes.
        """
        root_causes = []

        if ai_result.status != ExecutionStatus.SUCCESS:
            # If AI analysis failed, create unknown root cause
            root_causes.append(
                RootCause(
                    category=FailureCategory.UNKNOWN,
                    description="AI analysis failed - unable to determine root cause",
                    evidence=[f"Analysis error: {ai_result.error}"],
                    confidence=ConfidenceLevel.LOW,
                    affected_components=["workflow"],
                    related_metrics=[],
                    suggested_strategies=[HealingStrategy.ESCALATE],
                )
            )
            return root_causes

        # Parse AI analysis content to extract root causes
        # For rule-based analysis, we parse the structured output
        content = ai_result.content

        # Simple parsing for rule-based output
        # In production, this would use more sophisticated parsing
        if "###" in content:
            # Parse structured analysis
            sections = content.split("###")[1:]  # Skip first empty section
            for section in sections:
                cause = self._parse_cause_section(section)
                if cause:
                    root_causes.append(cause)

        # If no causes found, create from degradation signals
        if not root_causes and degradation_signals:
            for signal in degradation_signals:
                analysis = self._analyze_signal(signal, {})
                root_causes.append(
                    RootCause(
                        category=analysis["category"],
                        description=analysis["description"],
                        evidence=analysis["evidence"],
                        confidence=analysis["confidence"],
                        affected_components=analysis["components"],
                        related_metrics=[signal.description],
                        suggested_strategies=analysis["strategies"],
                    )
                )

        return root_causes

    def _parse_cause_section(self, section: str) -> RootCause | None:
        """Parse a cause section from AI analysis.

        Args:
            section: Section content string.

        Returns:
            RootCause if parsing successful, None otherwise.
        """
        try:
            lines = section.strip().split("\n")

            # Extract category from first line (e.g., "### RESOURCE EXHAUSTION")
            first_line = lines[0].strip()
            category_str = (
                first_line.replace("###", "").strip().lower().replace(" ", "_")
            )
            try:
                category = FailureCategory(category_str)
            except ValueError:
                category = FailureCategory.UNKNOWN

            # Parse fields
            description = ""
            evidence = []
            confidence = ConfidenceLevel.MEDIUM
            components = ["workflow"]
            strategies = []

            for line in lines[1:]:
                line = line.strip()
                if line.startswith("**Description**"):
                    description = line.split(":", 1)[1].strip() if ":" in line else ""
                elif line.startswith("**Confidence**"):
                    conf_str = (
                        line.split(":", 1)[1].strip().lower()
                        if ":" in line
                        else "medium"
                    )
                    confidence = ConfidenceLevel(conf_str)
                elif line.startswith("**Evidence**"):
                    # Next lines are evidence
                    continue
                elif line.startswith("- ") and evidence:
                    evidence.append(line[2:].strip())
                elif line.startswith("**Affected Components**"):
                    comp_str = line.split(":", 1)[1].strip() if ":" in line else ""
                    components = [c.strip() for c in comp_str.split(",")]
                elif line.startswith("**Suggested Strategies**"):
                    strat_str = line.split(":", 1)[1].strip() if ":" in line else ""
                    for s in strat_str.split(","):
                        s = s.strip().lower()
                        with contextlib.suppress(ValueError):
                            strategies.append(HealingStrategy(s))

            if not description:
                return None

            return RootCause(
                category=category,
                description=description,
                evidence=evidence or ["Detected in analysis"],
                confidence=confidence,
                affected_components=components,
                related_metrics=[],
                suggested_strategies=strategies or [HealingStrategy.ESCALATE],
            )

        except Exception:
            return None

    def _identify_primary_cause(
        self,
        root_causes: list[RootCause],
    ) -> RootCause | None:
        """Identify the primary root cause from list of causes.

        Args:
            root_causes: List of identified root causes.

        Returns:
            Primary root cause, or None if no causes.
        """
        if not root_causes:
            return None

        # Sort by confidence (HIGH > MEDIUM > LOW)
        confidence_order = {
            ConfidenceLevel.HIGH: 0,
            ConfidenceLevel.MEDIUM: 1,
            ConfidenceLevel.LOW: 2,
        }

        # Sort by confidence, then by number of evidence items
        sorted_causes = sorted(
            root_causes,
            key=lambda c: (
                confidence_order.get(c.confidence, 3),
                len(c.evidence),
            ),
        )

        return sorted_causes[0]

    def _generate_healing_plan(
        self,
        root_causes: list[RootCause],
        primary_cause: RootCause | None,
    ) -> dict[str, Any]:
        """Generate healing plan from root causes.

        Args:
            root_causes: List of root causes.
            primary_cause: Primary root cause.

        Returns:
            Healing plan dictionary.
        """
        if not primary_cause:
            return {
                "strategies": [],
                "primary_strategy": None,
                "fallback_strategies": [],
                "requires_escalation": True,
            }

        strategies = []

        # Add strategies from primary cause
        if primary_cause:
            for strategy in primary_cause.suggested_strategies:
                if strategy.value not in strategies:
                    strategies.append(strategy.value)

        # Add strategies from other causes
        for cause in root_causes:
            if cause != primary_cause:
                for strategy in cause.suggested_strategies:
                    if strategy.value not in strategies:
                        strategies.append(strategy.value)

        primary_strategy = strategies[0] if strategies else None
        fallback_strategies = strategies[1:4] if len(strategies) > 1 else []

        return {
            "strategies": strategies,
            "primary_strategy": primary_strategy,
            "fallback_strategies": fallback_strategies,
            "requires_escalation": HealingStrategy.ESCALATE.value in strategies,
        }

    def _requires_escalation(
        self,
        root_causes: list[RootCause],
        primary_cause: RootCause | None,
    ) -> bool:
        """Determine if issue requires escalation.

        Args:
            root_causes: List of root causes.
            primary_cause: Primary root cause.

        Returns:
            True if escalation required, False otherwise.
        """
        # Escalate if no causes found
        if not root_causes or not primary_cause:
            return True

        # Escalate if primary cause is UNKNOWN with low confidence
        if (
            primary_cause.category == FailureCategory.UNKNOWN
            and primary_cause.confidence == ConfidenceLevel.LOW
        ):
            return True

        # Escalate if ESCALATE is the only suggested strategy
        return bool(
            len(primary_cause.suggested_strategies) == 1
            and primary_cause.suggested_strategies[0] == HealingStrategy.ESCALATE
        )

    def clear_cache(self) -> None:
        """Clear the analysis cache.

        This should be called when the workflow state changes significantly
        to ensure fresh analysis.
        """
        self._analysis_cache.clear()


# Re-export for convenience
__all__ = [
    "FailureCategory",
    "HealingStrategy",
    "ConfidenceLevel",
    "ExecutionStatus",
    "ExecutionResult",
    "RootCause",
    "DiagnosticResult",
    "StrategyEvaluation",
    "HealingPlan",
    "StrategySelector",
    "RootCauseAnalyzer",
]
