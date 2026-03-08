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
