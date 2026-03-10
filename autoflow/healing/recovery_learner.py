"""Recovery learning models and pattern extraction for automated error recovery.

This module provides data models and learning capabilities for analyzing recovery
attempts, identifying successful patterns, and building knowledge about which
strategies work best for specific error types. It integrates with the healing
system to provide intelligent, adaptive recovery that improves over time.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
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

    # Define ordering for comparison
    def __ge__(self, other: "PatternConfidence") -> bool:
        """Greater than or equal comparison."""
        order = {PatternConfidence.LOW: 0, PatternConfidence.MEDIUM: 1, PatternConfidence.HIGH: 2}
        return order[self] >= order[other]

    def __gt__(self, other: "PatternConfidence") -> bool:
        """Greater than comparison."""
        order = {PatternConfidence.LOW: 0, PatternConfidence.MEDIUM: 1, PatternConfidence.HIGH: 2}
        return order[self] > order[other]

    def __le__(self, other: "PatternConfidence") -> bool:
        """Less than or equal comparison."""
        order = {PatternConfidence.LOW: 0, PatternConfidence.MEDIUM: 1, PatternConfidence.HIGH: 2}
        return order[self] <= order[other]

    def __lt__(self, other: "PatternConfidence") -> bool:
        """Less than comparison."""
        order = {PatternConfidence.LOW: 0, PatternConfidence.MEDIUM: 1, PatternConfidence.HIGH: 2}
        return order[self] < order[other]


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


class RecoveryLearner:
    """Learns from recovery attempts to improve automated error recovery.

    This class records recovery attempts, analyzes historical data to identify
    successful patterns, and maintains learned strategies for future error recovery.
    It follows the pattern from FeedbackCollector for data persistence and
    WorkflowHealthMonitor for statistics tracking.

    Example:
        learner = RecoveryLearner()
        learner.record_attempt(
            pattern_id="timeout-error-123",
            strategy_used="retry_with_backoff",
            action_type="RETRY",
            parameters={"max_retries": 3, "backoff": "exponential"},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=5.2,
        )
        patterns = learner.learn_from_history()
    """

    # Default path for recovery learning data
    DEFAULT_LEARNING_PATH = Path(".autoflow/recovery_learning.json")

    def __init__(
        self,
        learning_path: Path | None = None,
        root_dir: Path | None = None,
    ) -> None:
        """Initialize the recovery learner.

        Args:
            learning_path: Path to learning data JSON file. If None, uses DEFAULT_LEARNING_PATH.
            root_dir: Root directory of the project. Defaults to current directory.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if learning_path is None:
            learning_path = self.DEFAULT_LEARNING_PATH

        self.learning_path = Path(learning_path)

        # Ensure parent directory exists
        self.learning_path.parent.mkdir(parents=True, exist_ok=True)

        # Storage for recovery attempts and learned knowledge
        self._attempts: dict[str, RecoveryAttempt] = {}
        self._patterns: dict[str, RecoveryPattern] = {}
        self._learned_strategies: dict[str, LearnedStrategy] = {}

        # Load existing learning data or initialize empty
        self._load_learning_data()

    def record_attempt(
        self,
        pattern_id: str,
        strategy_used: str,
        action_type: str,
        parameters: dict[str, Any],
        outcome: RecoveryOutcome,
        success: bool,
        execution_time: float = 0.0,
        error: str | None = None,
        changes_made: list[str] | None = None,
        verification_passed: bool = False,
        outcome_details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a recovery attempt for learning.

        Creates a new recovery attempt record with timestamp and metadata.
        Updates pattern statistics and learned strategies based on the outcome.
        Persists all data to disk for future learning.

        Args:
            pattern_id: Identifier for the error pattern this attempt addressed.
            strategy_used: The healing strategy that was applied.
            action_type: Type of healing action executed (e.g., RETRY, RECONFIGURE).
            parameters: Parameters used for this recovery attempt.
            outcome: Final outcome of the recovery attempt.
            success: Whether the recovery attempt was successful.
            execution_time: Time taken to execute the recovery in seconds.
            error: Error message if the recovery attempt failed.
            changes_made: List of changes made during this recovery attempt.
            verification_passed: Whether post-recovery verification passed.
            outcome_details: Human-readable details about the outcome.
            metadata: Additional context and diagnostic information.

        Returns:
            The unique attempt_id for the recorded attempt.

        Raises:
            IOError: If unable to write learning data to disk.
        """
        # Generate unique attempt ID
        attempt_id = str(uuid.uuid4())

        # Create recovery attempt record
        attempt = RecoveryAttempt(
            attempt_id=attempt_id,
            pattern_id=pattern_id,
            timestamp=datetime.now(UTC),
            strategy_used=strategy_used,
            action_type=action_type,
            parameters=parameters,
            outcome=outcome,
            success=success,
            error=error,
            execution_time=execution_time,
            changes_made=changes_made or [],
            verification_passed=verification_passed,
            outcome_details=outcome_details,
            metadata=metadata or {},
        )

        # Store in memory
        self._attempts[attempt_id] = attempt

        # Update or create pattern
        if pattern_id not in self._patterns:
            self._patterns[pattern_id] = RecoveryPattern(
                pattern_id=pattern_id,
                error_category=metadata.get("error_category", "unknown")
                if metadata
                else "unknown",
                error_signature=metadata.get("error_signature", "")
                if metadata
                else "",
                features=metadata.get("features", {}) if metadata else {},
            )

        # Update pattern statistics
        pattern = self._patterns[pattern_id]
        pattern.occurrence_count += 1
        pattern.last_seen = datetime.now(UTC)
        if strategy_used not in pattern.related_strategies:
            pattern.related_strategies.append(strategy_used)
        if success:
            pattern.success_count += 1
        else:
            pattern.failure_count += 1
        pattern.update_confidence()

        # Update or create learned strategy
        strategy_key = f"{pattern_id}:{strategy_used}"
        if strategy_key not in self._learned_strategies:
            self._learned_strategies[strategy_key] = LearnedStrategy(
                strategy_id=strategy_key,
                pattern_id=pattern_id,
                strategy_name=strategy_used,
                strategy_type=action_type,
                description=f"Learned strategy for {pattern_id}",
                success_rate=0.0,
                total_attempts=0,
                successful_attempts=0,
                failed_attempts=0,
                avg_execution_time=0.0,
                optimal_parameters=parameters.copy(),
                confidence=PatternConfidence.LOW,
            )

        # Update learned strategy statistics
        self._learned_strategies[strategy_key].update_statistics(
            success=success,
            execution_time=execution_time,
            parameters=parameters if success else None,
        )

        # Persist to disk
        self._save_learning_data()

        return attempt_id

    def learn_from_history(
        self,
        min_attempts: int = 3,
        min_success_rate: float = 0.5,
    ) -> list[LearnedStrategy]:
        """Analyze historical recovery attempts to extract successful patterns.

        Reviews all recorded recovery attempts, identifies patterns in successful
        recoveries, and returns recommended strategies sorted by effectiveness.

        Args:
            min_attempts: Minimum number of attempts required to consider a pattern learned.
            min_success_rate: Minimum success rate required to recommend a strategy.

        Returns:
            List of recommended LearnedStrategy objects sorted by effectiveness_score.

        Raises:
            IOError: If unable to read learning data.
        """
        recommended_strategies = []

        for strategy in self._learned_strategies.values():
            # Filter based on thresholds
            if (
                strategy.total_attempts >= min_attempts
                and strategy.success_rate >= min_success_rate
                and strategy.is_recommended()
            ):
                recommended_strategies.append(strategy)

        # Sort by effectiveness score (highest first)
        recommended_strategies.sort(
            key=lambda s: (s.effectiveness_score, s.success_rate), reverse=True
        )

        return recommended_strategies

    def get_pattern_statistics(self, pattern_id: str) -> dict[str, Any] | None:
        """Get statistics for a specific error pattern.

        Args:
            pattern_id: The pattern identifier to look up.

        Returns:
            Dictionary with pattern statistics, or None if pattern not found.
        """
        if pattern_id not in self._patterns:
            return None

        pattern = self._patterns[pattern_id]
        return {
            "pattern_id": pattern.pattern_id,
            "error_category": pattern.error_category,
            "occurrence_count": pattern.occurrence_count,
            "first_seen": pattern.first_seen.isoformat(),
            "last_seen": pattern.last_seen.isoformat(),
            "success_rate": pattern.get_success_rate(),
            "confidence": pattern.confidence.value,
            "related_strategies": pattern.related_strategies,
        }

    def get_best_strategy(
        self, pattern_id: str, min_confidence: PatternConfidence = PatternConfidence.MEDIUM
    ) -> LearnedStrategy | None:
        """Get the best learned strategy for a given pattern.

        Args:
            pattern_id: The pattern identifier to find a strategy for.
            min_confidence: Minimum confidence level required.

        Returns:
            The best LearnedStrategy for this pattern, or None if no suitable strategy found.
        """
        # Find all strategies for this pattern
        pattern_strategies = [
            s
            for s in self._learned_strategies.values()
            if s.pattern_id == pattern_id and s.confidence.value >= min_confidence.value
        ]

        if not pattern_strategies:
            return None

        # Return the one with highest effectiveness score
        return max(pattern_strategies, key=lambda s: s.effectiveness_score)

    def get_all_attempts(
        self, pattern_id: str | None = None, limit: int | None = None
    ) -> list[RecoveryAttempt]:
        """Get recovery attempts, optionally filtered by pattern.

        Args:
            pattern_id: If specified, only return attempts for this pattern.
            limit: Maximum number of attempts to return (most recent first).

        Returns:
            List of RecoveryAttempt objects.
        """
        attempts = list(self._attempts.values())

        # Filter by pattern if specified
        if pattern_id is not None:
            attempts = [a for a in attempts if a.pattern_id == pattern_id]

        # Sort by timestamp (most recent first)
        attempts.sort(key=lambda a: a.timestamp, reverse=True)

        # Apply limit if specified
        if limit is not None:
            attempts = attempts[:limit]

        return attempts

    def get_learning_summary(self) -> dict[str, Any]:
        """Get comprehensive summary of learning data.

        Returns:
            Dictionary with statistics about attempts, patterns, and learned strategies.
        """
        total_attempts = len(self._attempts)
        total_patterns = len(self._patterns)
        total_strategies = len(self._learned_strategies)

        # Count successful vs failed attempts
        successful_attempts = sum(1 for a in self._attempts.values() if a.success)
        failed_attempts = total_attempts - successful_attempts

        # Count strategies by confidence
        high_confidence = sum(
            1 for s in self._learned_strategies.values() if s.confidence == PatternConfidence.HIGH
        )
        medium_confidence = sum(
            1
            for s in self._learned_strategies.values()
            if s.confidence == PatternConfidence.MEDIUM
        )
        low_confidence = sum(
            1 for s in self._learned_strategies.values() if s.confidence == PatternConfidence.LOW
        )

        return {
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "overall_success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0.0,
            "total_patterns": total_patterns,
            "total_learned_strategies": total_strategies,
            "strategies_by_confidence": {
                "high": high_confidence,
                "medium": medium_confidence,
                "low": low_confidence,
            },
        }

    def calculate_confidence(self, success_rate: float, sample_size: int) -> float:
        """Calculate confidence score based on sample size and success rate.

        This method computes a continuous confidence score between 0.0 and 1.0
        that combines both the success rate of a strategy and the amount of
        data (sample size) available. Higher success rates and larger sample
        sizes result in higher confidence scores.

        The calculation follows these principles:
        - Success rate is the primary factor: higher success = higher confidence
        - Sample size provides a multiplier: more data = more confidence
        - Minimum samples needed for any meaningful confidence
        - Diminishing returns on sample size beyond a threshold

        Args:
            success_rate: Proportion of successful attempts (0.0 to 1.0).
            sample_size: Total number of attempts observed.

        Returns:
            Confidence score between 0.0 and 1.0.

        Examples:
            >>> learner = RecoveryLearner()
            >>> # High success rate with good sample size
            >>> confidence = learner.calculate_confidence(0.85, 10)
            >>> print(f"{confidence:.2f}")  # e.g., 0.92
            >>> # Moderate success rate with limited samples
            >>> confidence = learner.calculate_confidence(0.65, 3)
            >>> print(f"{confidence:.2f}")  # e.g., 0.55
            >>> # Low success rate regardless of sample size
            >>> confidence = learner.calculate_confidence(0.40, 20)
            >>> print(f"{confidence:.2f}")  # e.g., 0.32
        """
        # Input validation
        if not 0.0 <= success_rate <= 1.0:
            raise ValueError(f"success_rate must be between 0.0 and 1.0, got {success_rate}")
        if sample_size < 0:
            raise ValueError(f"sample_size must be non-negative, got {sample_size}")

        # No data means no confidence
        if sample_size == 0:
            return 0.0

        # Calculate sample size multiplier (0.0 to 1.0)
        # Uses logarithmic scaling with diminishing returns
        # - 1-2 samples: very low multiplier (0.1-0.3)
        # - 3-5 samples: low to moderate multiplier (0.4-0.6)
        # - 5-10 samples: moderate multiplier (0.7-0.8)
        # - 10+ samples: high multiplier (0.9-1.0)
        import math

        # Minimum samples for baseline confidence
        min_samples = 2
        # Point of diminishing returns (additional samples matter less)
        saturation_point = 10

        if sample_size < min_samples:
            # Very limited data
            sample_multiplier = 0.1 * (sample_size / min_samples)
        else:
            # Logarithmic scaling with diminishing returns
            # Maps [min_samples, infinity) to [0.3, 1.0)
            log_sample = math.log(sample_size - min_samples + 1)
            log_saturation = math.log(saturation_point - min_samples + 1)
            # Scale to [0.3, 1.0) range
            sample_multiplier = 0.3 + 0.7 * min(log_sample / log_saturation, 1.0)

        # Calculate confidence score
        # Success rate is weighted more heavily than sample size
        # - Success rate: 70% weight
        # - Sample size: 30% weight
        confidence = (success_rate * 0.7) + (sample_multiplier * 0.3)

        # Ensure result is in valid range
        return max(0.0, min(1.0, confidence))

    def clear_old_data(self, keep_recent: int = 1000) -> int:
        """Remove old recovery attempts to manage storage.

        Keeps the most recent N attempts and removes older ones.
        Patterns and learned strategies are preserved as they represent learned knowledge.

        Args:
            keep_recent: Number of recent attempts to keep.

        Returns:
            Number of attempts removed.

        Raises:
            IOError: If unable to write learning data to disk.
        """
        if len(self._attempts) <= keep_recent:
            return 0

        # Sort attempts by timestamp (most recent first)
        sorted_attempts = sorted(
            self._attempts.items(),
            key=lambda x: x[1].timestamp,
            reverse=True,
        )

        # Keep only the most recent
        kept = dict(sorted_attempts[:keep_recent])
        removed = len(self._attempts) - len(kept)
        self._attempts = kept

        # Persist to disk
        self._save_learning_data()

        return removed

    def _load_learning_data(self) -> None:
        """Load learning data from disk.

        Reads the learning JSON file and populates attempts, patterns, and strategies.
        Creates an empty learning file if none exists.
        """
        if not self.learning_path.exists():
            # Create empty learning file
            self._save_learning_data()
            return

        try:
            data = json.loads(self.learning_path.read_text(encoding="utf-8"))

            # Load attempts
            attempts_data = data.get("attempts", {})
            self._attempts = {
                attempt_id: RecoveryAttempt.from_dict(attempt_data)
                for attempt_id, attempt_data in attempts_data.items()
            }

            # Load patterns
            patterns_data = data.get("patterns", {})
            self._patterns = {
                pattern_id: RecoveryPattern(
                    pattern_id=p["pattern_id"],
                    error_category=p["error_category"],
                    error_signature=p["error_signature"],
                    features=p["features"],
                    occurrence_count=p.get("occurrence_count", 1),
                    first_seen=datetime.fromisoformat(p["first_seen"]),
                    last_seen=datetime.fromisoformat(p["last_seen"]),
                    related_strategies=p.get("related_strategies", []),
                    success_count=p.get("success_count", 0),
                    failure_count=p.get("failure_count", 0),
                    confidence=PatternConfidence(p.get("confidence", PatternConfidence.LOW.value)),
                    metadata=p.get("metadata", {}),
                )
                for pattern_id, p in patterns_data.items()
            }

            # Load learned strategies
            strategies_data = data.get("learned_strategies", {})
            self._learned_strategies = {
                strategy_id: LearnedStrategy.from_dict(strategy_data)
                for strategy_id, strategy_data in strategies_data.items()
            }
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self._attempts = {}
            self._patterns = {}
            self._learned_strategies = {}

    def _save_learning_data(self) -> None:
        """Save learning data to disk.

        Writes attempts, patterns, and strategies to the learning JSON file.
        Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the learning file.
        """
        # Convert to dictionaries
        attempts_data = {
            attempt_id: attempt.to_dict()
            for attempt_id, attempt in self._attempts.items()
        }
        patterns_data = {
            pattern_id: pattern.to_dict()
            for pattern_id, pattern in self._patterns.items()
        }
        strategies_data = {
            strategy_id: strategy.to_dict()
            for strategy_id, strategy in self._learned_strategies.items()
        }

        # Build learning data structure
        learning_data = {
            "attempts": attempts_data,
            "patterns": patterns_data,
            "learned_strategies": strategies_data,
            "metadata": {
                "total_attempts": len(self._attempts),
                "total_patterns": len(self._patterns),
                "total_strategies": len(self._learned_strategies),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.learning_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(learning_data, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.learning_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to write learning data to {self.learning_path}: {e}") from e

    def extract_pattern(
        self,
        root_cause: "RootCause",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract error pattern from diagnostic result.

        Analyzes a root cause to generate a unique error signature and extract
        features for pattern matching. This enables the system to identify similar
        errors in the future and apply learned recovery strategies.

        The pattern extraction process normalizes error messages to identify
        the underlying error type while ignoring specific values (like file paths,
        line numbers, timestamps) that vary between occurrences.

        Args:
            root_cause: The RootCause object from diagnostic analysis.
            context: Additional context about the error (e.g., task_id, workflow_id,
                error_message, stack_trace).

        Returns:
            Dictionary containing:
                - pattern_id: Unique identifier for this error pattern.
                - error_category: Category of the error.
                - error_signature: Normalized error signature.
                - features: Feature vector for pattern matching.

        Raises:
            ValueError: If root_cause is None or missing required fields.
        """
        if root_cause is None:
            raise ValueError("root_cause cannot be None")

        context = context or {}

        # Extract basic error information
        error_category = root_cause.category.value
        description = root_cause.description
        affected_components = root_cause.affected_components

        # Generate normalized error signature
        error_signature = self._generate_error_signature(
            error_category=error_category,
            description=description,
            affected_components=affected_components,
            error_message=context.get("error_message", ""),
        )

        # Generate unique pattern ID from signature
        pattern_id = self._generate_pattern_id(error_signature)

        # Extract feature vector for ML-based pattern matching
        features = self._extract_features(
            root_cause=root_cause,
            context=context,
        )

        return {
            "pattern_id": pattern_id,
            "error_category": error_category,
            "error_signature": error_signature,
            "features": features,
        }

    def _generate_error_signature(
        self,
        error_category: str,
        description: str,
        affected_components: list[str],
        error_message: str = "",
    ) -> str:
        """Generate normalized error signature for pattern matching.

        Creates a unique signature that identifies the error type while
        normalizing away variable elements like file paths, line numbers,
        and specific values.

        Args:
            error_category: Category of the error.
            description: Human-readable description of the root cause.
            affected_components: List of components affected by this issue.
            error_message: Original error message (if available).

        Returns:
            Normalized error signature string.
        """
        # Normalize the description
        normalized_desc = self._normalize_error_text(description)

        # Normalize error message if provided
        normalized_error = ""
        if error_message:
            normalized_error = self._normalize_error_message(error_message)

        # Build signature from category, normalized description, and components
        signature_parts = [
            error_category,
            normalized_desc,
        ]

        # Add affected components if available
        if affected_components:
            # Sort for consistency
            components_sorted = sorted(affected_components)
            signature_parts.append(",".join(components_sorted))

        # Add normalized error message if it provides additional context
        if normalized_error and normalized_error != "unknown_error":
            signature_parts.append(normalized_error)

        # Join with delimiter
        signature = "|".join(signature_parts)

        return signature

    def _normalize_error_message(self, error: str) -> str:
        """Normalize error message for pattern matching.

        Removes file paths, line numbers, and specific values to extract
        the underlying error pattern. Follows the pattern from WorkflowHealthMonitor.

        Args:
            error: Raw error message.

        Returns:
            Normalized error key.
        """
        # Remove file paths, line numbers, and specific values
        normalized = error

        # Remove file paths like /path/to/file.py
        normalized = re.sub(r"[/\w\-_\.]+\.py", "<file>", normalized)
        normalized = re.sub(r"[/\w\-_\.]+\.js", "<file>", normalized)
        normalized = re.sub(r"[/\w\-_\.]+\.ts", "<file>", normalized)

        # Remove line numbers like :123
        normalized = re.sub(r":\d+", ":<line>", normalized)

        # Remove hexadecimal addresses like 0x12345678
        normalized = re.sub(r"0x[0-9a-fA-F]+", "<addr>", normalized)

        # Remove UUIDs
        normalized = re.sub(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            "<uuid>",
            normalized,
        )

        # Remove specific numbers but keep error codes
        normalized = re.sub(r"\b\d{3,}\b", "<num>", normalized)

        # Get first part (before colon if present)
        normalized = normalized.split(":")[0]

        # Clean up whitespace
        normalized = normalized.strip()

        return normalized or "unknown_error"

    def _normalize_error_text(self, text: str) -> str:
        """Normalize error description text for pattern matching.

        Args:
            text: Error description text.

        Returns:
            Normalized text.
        """
        # Convert to lowercase
        normalized = text.lower()

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Remove specific values (numbers, quotes)
        normalized = re.sub(r'\b\d+\b', "<num>", normalized)
        normalized = re.sub(r'["\'].*?["\']', "<value>", normalized)

        # Remove common filler words
        filler_words = ["the", "a", "an", "is", "was", "been", "has", "have"]
        for word in filler_words:
            normalized = re.sub(rf"\b{word}\b", "", normalized)

        # Clean up again
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _generate_pattern_id(self, error_signature: str) -> str:
        """Generate unique pattern ID from error signature.

        Creates a consistent, readable pattern ID from the error signature.

        Args:
            error_signature: Normalized error signature.

        Returns:
            Unique pattern identifier.
        """
        import hashlib

        # Create hash of signature for uniqueness
        hash_obj = hashlib.md5(error_signature.encode())
        short_hash = hash_obj.hexdigest()[:8]

        # Extract category from signature (first part before |)
        category = error_signature.split("|")[0] if error_signature else "unknown"

        # Create readable pattern ID
        pattern_id = f"{category}-{short_hash}"

        return pattern_id

    def _extract_features(
        self,
        root_cause: "RootCause",
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract feature vector for ML-based pattern matching.

        Creates a feature vector that captures the characteristics of the error
        for use in machine learning-based pattern matching and similarity detection.

        Args:
            root_cause: The RootCause object from diagnostic analysis.
            context: Additional context about the error.

        Returns:
            Feature vector as a dictionary.
        """
        features = {
            # Error category
            "error_category": root_cause.category.value,
            # Component information
            "affected_components": root_cause.affected_components,
            "component_count": len(root_cause.affected_components),
            # Confidence level
            "confidence": root_cause.confidence.value,
            # Related metrics
            "related_metrics": root_cause.related_metrics,
            "metric_count": len(root_cause.related_metrics),
            # Suggested strategies
            "suggested_strategies": [s.value for s in root_cause.suggested_strategies],
            # Context features
            "has_stack_trace": bool(context.get("stack_trace")),
            "has_error_message": bool(context.get("error_message")),
            "task_id": context.get("task_id", ""),
            "workflow_id": context.get("workflow_id", ""),
        }

        # Add error message features if available
        error_message = context.get("error_message", "")
        if error_message:
            features["error_message_length"] = len(error_message)
            features["error_has_file_path"] = "/" in error_message or "\\" in error_message
            features["error_has_line_number"] = bool(re.search(r":\d+", error_message))

        # Add description features
        if root_cause.description:
            features["description_length"] = len(root_cause.description)
            features["description_word_count"] = len(root_cause.description.split())

        return features

    def recommend_strategy(
        self,
        root_cause: "RootCause",
        context: dict[str, Any] | None = None,
        min_confidence: PatternConfidence = PatternConfidence.MEDIUM,
    ) -> dict[str, Any] | None:
        """Recommend the best recovery strategy based on historical performance.

        Analyzes the root cause to identify the error pattern, then looks up
        learned strategies for similar patterns. Returns the strategy with the
        highest effectiveness score and success rate.

        Args:
            root_cause: The RootCause object from diagnostic analysis.
            context: Additional context about the error (e.g., task_id, workflow_id,
                error_message, stack_trace).
            min_confidence: Minimum confidence level required for recommendation.

        Returns:
            Dictionary containing:
                - strategy: The LearnedStrategy object (as dict)
                - pattern_id: The error pattern identifier
                - success_rate: Historical success rate for this strategy
                - confidence: Confidence level in this recommendation
                - rationale: Human-readable explanation of the recommendation
                - alternative_strategies: List of alternative strategies (if any)
            Returns None if no suitable strategy found or pattern has insufficient data.
        """
        if root_cause is None:
            return None

        context = context or {}

        # Extract pattern from root cause
        try:
            pattern_info = self.extract_pattern(root_cause, context)
            pattern_id = pattern_info["pattern_id"]
        except (ValueError, KeyError):
            return None

        # Get all strategies for this pattern
        pattern_strategies = [
            s
            for s in self._learned_strategies.values()
            if s.pattern_id == pattern_id and s.confidence >= min_confidence
        ]

        if not pattern_strategies:
            return None

        # Sort by effectiveness score (highest first)
        pattern_strategies.sort(
            key=lambda s: (s.effectiveness_score, s.success_rate), reverse=True
        )

        # Get the best strategy
        best_strategy = pattern_strategies[0]

        # Get alternative strategies (up to 3)
        alternatives = pattern_strategies[1:4]

        # Build rationale
        rationale_parts = [
            f"Strategy '{best_strategy.strategy_name}' has been attempted "
            f"{best_strategy.total_attempts} times for this error pattern, "
            f"with a success rate of {best_strategy.success_rate:.1%}.",
        ]

        if best_strategy.effectiveness_score > 0.8:
            rationale_parts.append("High effectiveness score indicates this strategy is reliable.")
        elif best_strategy.effectiveness_score > 0.6:
            rationale_parts.append("Moderate effectiveness score suggests this strategy is reasonably effective.")
        else:
            rationale_parts.append("Lower effectiveness score suggests this strategy may require monitoring.")

        if best_strategy.avg_execution_time > 0:
            rationale_parts.append(
                f"Average execution time: {best_strategy.avg_execution_time:.1f}s."
            )

        # Add confidence rationale
        if best_strategy.confidence == PatternConfidence.HIGH:
            rationale_parts.append(
                "High confidence: Based on sufficient successful attempts with strong performance."
            )
        elif best_strategy.confidence == PatternConfidence.MEDIUM:
            rationale_parts.append(
                "Medium confidence: Based on moderate historical data with acceptable performance."
            )
        else:
            rationale_parts.append(
                "Low confidence: Limited historical data or inconsistent performance."
            )

        rationale = " ".join(rationale_parts)

        return {
            "strategy": best_strategy.to_dict(),
            "pattern_id": pattern_id,
            "success_rate": best_strategy.success_rate,
            "confidence": best_strategy.confidence.value,
            "rationale": rationale,
            "alternative_strategies": [s.to_dict() for s in alternatives],
        }

    def reset(self) -> None:
        """Reset all learning data.

        Clears all attempts, patterns, and learned strategies.
        Use with caution as this loses all learned knowledge.
        """
        self._attempts.clear()
        self._patterns.clear()
        self._learned_strategies.clear()
        self._save_learning_data()
