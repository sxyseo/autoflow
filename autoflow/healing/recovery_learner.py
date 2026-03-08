"""Recovery learning models and pattern extraction for automated error recovery.

This module provides data models and learning capabilities for analyzing recovery
attempts, identifying successful patterns, and building knowledge about which
strategies work best for specific error types. It integrates with the healing
system to provide intelligent, adaptive recovery that improves over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autoflow.healing.diagnostic import (
        FailureCategory,
        HealingStrategy,
        RootCause,
    )


class PatternConfidence(Enum):
    """Confidence levels for learned recovery patterns."""

    HIGH = "high"  # >80% success rate with sufficient samples
    MEDIUM = "medium"  # 50-80% success rate or limited samples
    LOW = "low"  # <50% success rate or very limited samples


class RecoveryOutcome(str, Enum):
    """Possible outcomes of a recovery attempt.

    Attributes:
        SUCCESS: Recovery attempt fully resolved the issue.
        PARTIAL: Recovery attempt partially resolved the issue.
        FAILED: Recovery attempt failed to resolve the issue.
        ESCALATED: Recovery attempt was escalated to human operator.
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass
class RecoveryAttempt:
    """Record of a single recovery attempt with outcome and context.

    A RecoveryAttempt captures the details of an individual healing action
    that was executed in response to an error. It tracks what strategy was used,
    the parameters applied, the outcome achieved, and timing information.
    This data is used to build knowledge about which recovery strategies work
    best for specific error patterns.

    Attributes:
        attempt_id: Unique identifier for this recovery attempt.
        pattern_id: Reference to the error pattern this attempt addressed.
        timestamp: When this recovery attempt was executed (ISO format).
        strategy_used: The healing strategy that was applied.
        action_type: Type of healing action executed (e.g., RETRY, RECONFIGURE).
        parameters: Parameters used for this recovery attempt.
        outcome: Final outcome of the recovery attempt.
        success: Whether the recovery attempt was successful.
        error: Error message if the recovery attempt failed.
        execution_time: Time taken to execute the recovery in seconds.
        changes_made: List of changes made during this recovery attempt.
        verification_passed: Whether post-recovery verification passed.
        outcome_details: Human-readable details about the outcome.
        metadata: Additional context and diagnostic information.
    """

    attempt_id: str
    pattern_id: str
    timestamp: datetime
    strategy_used: str
    action_type: str
    parameters: dict[str, Any]
    outcome: RecoveryOutcome
    success: bool
    error: str | None = None
    execution_time: float = 0.0
    changes_made: list[str] = field(default_factory=list)
    verification_passed: bool = False
    outcome_details: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert recovery attempt to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the recovery attempt.
        """
        return {
            "attempt_id": self.attempt_id,
            "pattern_id": self.pattern_id,
            "timestamp": self.timestamp.isoformat(),
            "strategy_used": self.strategy_used,
            "action_type": self.action_type,
            "parameters": self.parameters,
            "outcome": self.outcome.value,
            "success": self.success,
            "error": self.error,
            "execution_time": self.execution_time,
            "changes_made": self.changes_made,
            "verification_passed": self.verification_passed,
            "outcome_details": self.outcome_details,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryAttempt":
        """Create recovery attempt from dictionary for JSON deserialization.

        Args:
            data: Dictionary containing recovery attempt data.

        Returns:
            RecoveryAttempt instance.
        """
        return cls(
            attempt_id=data["attempt_id"],
            pattern_id=data["pattern_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            strategy_used=data["strategy_used"],
            action_type=data["action_type"],
            parameters=data["parameters"],
            outcome=RecoveryOutcome(data["outcome"]),
            success=data["success"],
            error=data.get("error"),
            execution_time=data.get("execution_time", 0.0),
            changes_made=data.get("changes_made", []),
            verification_passed=data.get("verification_passed", False),
            outcome_details=data.get("outcome_details", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class RecoveryPattern:
    """Represents an error pattern with features for recovery learning.

    A RecoveryPattern captures the characteristics of a specific type of error
    that has occurred during workflow execution. It includes error signatures,
    feature vectors for ML-based pattern matching, and metadata for tracking
    pattern evolution over time.

    Attributes:
        pattern_id: Unique identifier for this pattern (generated from error signature).
        error_category: Category of the error (e.g., TIMEOUT, NETWORK_ISSUE).
        error_signature: Unique signature derived from error message and context.
        features: Feature vector describing the error context and environment.
        occurrence_count: Number of times this pattern has been observed.
        first_seen: Timestamp when this pattern was first observed.
        last_seen: Timestamp when this pattern was most recently observed.
        related_strategies: List of healing strategies that have been tried.
        success_count: Number of times recovery was successful for this pattern.
        failure_count: Number of times recovery failed for this pattern.
        confidence: Confidence level in the learned knowledge for this pattern.
        metadata: Additional context and diagnostic information.
    """

    pattern_id: str
    error_category: str
    error_signature: str
    features: dict[str, Any]
    occurrence_count: int = 1
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    related_strategies: list[str] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    confidence: PatternConfidence = PatternConfidence.LOW
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert recovery pattern to dictionary for serialization.

        Returns:
            Dictionary representation of the recovery pattern.
        """
        return {
            "pattern_id": self.pattern_id,
            "error_category": self.error_category,
            "error_signature": self.error_signature,
            "features": self.features,
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "related_strategies": self.related_strategies,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "confidence": self.confidence.value,
            "metadata": self.metadata,
        }

    def get_success_rate(self) -> float:
        """Calculate the success rate for this pattern.

        Returns:
            Success rate as a float between 0.0 and 1.0.
        """
        total_attempts = self.success_count + self.failure_count
        if total_attempts == 0:
            return 0.0
        return self.success_count / total_attempts

    def update_confidence(self) -> None:
        """Update confidence level based on success rate and sample size."""
        success_rate = self.get_success_rate()
        total_attempts = self.success_count + self.failure_count

        # Require at least 5 attempts for high confidence
        if success_rate > 0.8 and total_attempts >= 5:
            self.confidence = PatternConfidence.HIGH
        # Medium confidence: either good success rate with limited samples, or moderate success rate
        elif (success_rate > 0.6 and total_attempts >= 3) or (
            success_rate > 0.5 and total_attempts >= 5
        ):
            self.confidence = PatternConfidence.MEDIUM
        else:
            self.confidence = PatternConfidence.LOW


@dataclass
class LearnedStrategy:
    """Represents a learned successful strategy for recovering from error patterns.

    A LearnedStrategy captures knowledge about which recovery approaches have
    been successful for specific error patterns. It aggregates data from multiple
    recovery attempts to identify the most effective strategies, including optimal
    parameters, timing, and execution patterns. This enables the system to
    automatically select and apply proven recovery techniques.

    Attributes:
        strategy_id: Unique identifier for this learned strategy.
        pattern_id: Reference to the error pattern this strategy addresses.
        strategy_name: Human-readable name for this strategy.
        strategy_type: Type of healing strategy (e.g., RETRY, RECONFIGURE).
        description: Detailed description of what this strategy does.
        success_rate: Proportion of successful recoveries (0.0 to 1.0).
        total_attempts: Total number of times this strategy has been tried.
        successful_attempts: Number of times this strategy succeeded.
        failed_attempts: Number of times this strategy failed.
        avg_execution_time: Average execution time in seconds.
        optimal_parameters: Parameters that have shown best success.
        confidence: Confidence level in this learned strategy.
        first_learned: Timestamp when this strategy was first learned.
        last_successful_use: Timestamp when this strategy last succeeded.
        last_attempt: Timestamp when this strategy was last attempted.
        effectiveness_score: Combined score of success rate and efficiency.
        metadata: Additional context and diagnostic information.
    """

    strategy_id: str
    pattern_id: str
    strategy_name: str
    strategy_type: str
    description: str
    success_rate: float
    total_attempts: int
    successful_attempts: int
    failed_attempts: int
    avg_execution_time: float
    optimal_parameters: dict[str, Any]
    confidence: PatternConfidence
    first_learned: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_successful_use: datetime | None = None
    last_attempt: datetime | None = None
    effectiveness_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Calculate effectiveness score after initialization."""
        if self.effectiveness_score == 0.0:
            self.effectiveness_score = self._calculate_effectiveness_score()

    def to_dict(self) -> dict[str, Any]:
        """Convert learned strategy to dictionary for serialization.

        Returns:
            Dictionary representation of the learned strategy.
        """
        return {
            "strategy_id": self.strategy_id,
            "pattern_id": self.pattern_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "description": self.description,
            "success_rate": self.success_rate,
            "total_attempts": self.total_attempts,
            "successful_attempts": self.successful_attempts,
            "failed_attempts": self.failed_attempts,
            "avg_execution_time": self.avg_execution_time,
            "optimal_parameters": self.optimal_parameters,
            "confidence": self.confidence.value,
            "first_learned": self.first_learned.isoformat(),
            "last_successful_use": (
                self.last_successful_use.isoformat() if self.last_successful_use else None
            ),
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "effectiveness_score": self.effectiveness_score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedStrategy":
        """Create learned strategy from dictionary for deserialization.

        Args:
            data: Dictionary containing learned strategy data.

        Returns:
            LearnedStrategy instance.
        """
        return cls(
            strategy_id=data["strategy_id"],
            pattern_id=data["pattern_id"],
            strategy_name=data["strategy_name"],
            strategy_type=data["strategy_type"],
            description=data["description"],
            success_rate=data["success_rate"],
            total_attempts=data["total_attempts"],
            successful_attempts=data["successful_attempts"],
            failed_attempts=data["failed_attempts"],
            avg_execution_time=data["avg_execution_time"],
            optimal_parameters=data["optimal_parameters"],
            confidence=PatternConfidence(data["confidence"]),
            first_learned=datetime.fromisoformat(data["first_learned"]),
            last_successful_use=datetime.fromisoformat(data["last_successful_use"])
            if data.get("last_successful_use")
            else None,
            last_attempt=datetime.fromisoformat(data["last_attempt"])
            if data.get("last_attempt")
            else None,
            effectiveness_score=data.get("effectiveness_score", 0.0),
            metadata=data.get("metadata", {}),
        )

    def _calculate_effectiveness_score(self) -> float:
        """Calculate combined effectiveness score.

        Effectiveness combines success rate (70% weight) and execution efficiency (30% weight).
        Faster executions with high success rates score higher.

        Returns:
            Effectiveness score between 0.0 and 1.0.
        """
        # Success rate is primary factor (70% weight)
        success_weight = 0.7
        # Execution efficiency is secondary factor (30% weight)
        # Normalize execution time: assume 5 seconds is "fast", 60+ seconds is "slow"
        efficiency_weight = 0.3

        # Calculate efficiency score (inverse of execution time, normalized)
        if self.avg_execution_time > 0:
            # Using exponential decay: faster = much better
            efficiency_score = 1.0 / (1.0 + self.avg_execution_time / 10.0)
        else:
            efficiency_score = 1.0

        effectiveness = (self.success_rate * success_weight) + (
            efficiency_score * efficiency_weight
        )

        return round(effectiveness, 3)

    def update_statistics(
        self,
        success: bool,
        execution_time: float,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Update strategy statistics with a new recovery attempt result.

        Args:
            success: Whether the recovery attempt was successful.
            execution_time: Time taken for the recovery attempt in seconds.
            parameters: Parameters used in this attempt (if they should become optimal).
        """
        self.total_attempts += 1
        self.last_attempt = datetime.now(UTC)

        if success:
            self.successful_attempts += 1
            self.last_successful_use = datetime.now(UTC)
            # Update optimal parameters if provided
            if parameters is not None:
                self.optimal_parameters = parameters
        else:
            self.failed_attempts += 1

        # Recalculate success rate
        self.success_rate = self.successful_attempts / self.total_attempts

        # Update average execution time using moving average
        if self.avg_execution_time > 0:
            self.avg_execution_time = (
                (self.avg_execution_time * (self.total_attempts - 1) + execution_time)
                / self.total_attempts
            )
        else:
            self.avg_execution_time = execution_time

        # Recalculate effectiveness score
        self.effectiveness_score = self._calculate_effectiveness_score()

        # Update confidence level
        self._update_confidence()

    def _update_confidence(self) -> None:
        """Update confidence level based on success rate and sample size."""
        success_rate = self.success_rate
        total_attempts = self.total_attempts

        # High confidence: >80% success rate with at least 5 attempts
        if success_rate > 0.8 and total_attempts >= 5:
            self.confidence = PatternConfidence.HIGH
        # Medium confidence: either good success with some data, or moderate success with more data
        elif (success_rate > 0.6 and total_attempts >= 3) or (
            success_rate > 0.5 and total_attempts >= 5
        ):
            self.confidence = PatternConfidence.MEDIUM
        # Low confidence: insufficient data or poor success rate
        else:
            self.confidence = PatternConfidence.LOW

    def is_recommended(self) -> bool:
        """Determine if this strategy is recommended for use.

        A strategy is recommended if it has at least medium confidence
        and a success rate above 50%.

        Returns:
            True if the strategy is recommended for use.
        """
        return (
            self.confidence in (PatternConfidence.MEDIUM, PatternConfidence.HIGH)
            and self.success_rate > 0.5
        )
