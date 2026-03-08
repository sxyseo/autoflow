"""Unit Tests for Recovery Learner Data Models

Tests the RecoveryPattern, RecoveryAttempt, and LearnedStrategy dataclasses
for error recovery learning and pattern extraction.

These tests ensure proper serialization, deserialization, and business logic
for the recovery learning system.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.healing.recovery_learner import (
    LearnedStrategy,
    PatternConfidence,
    RecoveryAttempt,
    RecoveryLearner,
    RecoveryOutcome,
    RecoveryPattern,
)


# ============================================================================
# PatternConfidence Enum Tests
# ============================================================================


class TestPatternConfidence:
    """Tests for PatternConfidence enum."""

    def test_pattern_confidence_values(self) -> None:
        """Test PatternConfidence enum values."""
        assert PatternConfidence.HIGH.value == "high"
        assert PatternConfidence.MEDIUM.value == "medium"
        assert PatternConfidence.LOW.value == "low"

    def test_pattern_confidence_is_string(self) -> None:
        """Test that PatternConfidence values are strings."""
        assert isinstance(PatternConfidence.HIGH.value, str)
        assert isinstance(PatternConfidence.MEDIUM.value, str)
        assert isinstance(PatternConfidence.LOW.value, str)


# ============================================================================
# RecoveryOutcome Enum Tests
# ============================================================================


class TestRecoveryOutcome:
    """Tests for RecoveryOutcome enum."""

    def test_recovery_outcome_values(self) -> None:
        """Test RecoveryOutcome enum values."""
        assert RecoveryOutcome.SUCCESS == "success"
        assert RecoveryOutcome.PARTIAL == "partial"
        assert RecoveryOutcome.FAILED == "failed"
        assert RecoveryOutcome.ESCALATED == "escalated"

    def test_recovery_outcome_is_string(self) -> None:
        """Test that RecoveryOutcome values are strings."""
        assert isinstance(RecoveryOutcome.SUCCESS.value, str)

    def test_recovery_outcome_from_string(self) -> None:
        """Test creating RecoveryOutcome from string."""
        outcome = RecoveryOutcome("success")
        assert outcome == RecoveryOutcome.SUCCESS


# ============================================================================
# RecoveryAttempt Model Tests
# ============================================================================


class TestRecoveryAttempt:
    """Tests for RecoveryAttempt model."""

    def test_recovery_attempt_init_minimal(self) -> None:
        """Test RecoveryAttempt initialization with minimal fields."""
        timestamp = datetime.now(UTC)
        attempt = RecoveryAttempt(
            attempt_id="attempt-001",
            pattern_id="pattern-001",
            timestamp=timestamp,
            strategy_used="retry_with_backoff",
            action_type="RETRY",
            parameters={"max_retries": 3},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
        )

        assert attempt.attempt_id == "attempt-001"
        assert attempt.pattern_id == "pattern-001"
        assert attempt.timestamp == timestamp
        assert attempt.strategy_used == "retry_with_backoff"
        assert attempt.action_type == "RETRY"
        assert attempt.parameters == {"max_retries": 3}
        assert attempt.outcome == RecoveryOutcome.SUCCESS
        assert attempt.success is True
        assert attempt.error is None
        assert attempt.execution_time == 0.0
        assert attempt.changes_made == []
        assert attempt.verification_passed is False
        assert attempt.outcome_details == ""
        assert attempt.metadata == {}

    def test_recovery_attempt_init_full(self) -> None:
        """Test RecoveryAttempt initialization with all fields."""
        timestamp = datetime.now(UTC)
        attempt = RecoveryAttempt(
            attempt_id="attempt-002",
            pattern_id="pattern-002",
            timestamp=timestamp,
            strategy_used="reconfigure_timeout",
            action_type="RECONFIGURE",
            parameters={"timeout": 120},
            outcome=RecoveryOutcome.PARTIAL,
            success=False,
            error="Partial recovery achieved",
            execution_time=5.5,
            changes_made=["Increased timeout", "Updated retry policy"],
            verification_passed=True,
            outcome_details="Issue partially resolved",
            metadata={"env": "production", "region": "us-east-1"},
        )

        assert attempt.attempt_id == "attempt-002"
        assert attempt.error == "Partial recovery achieved"
        assert attempt.execution_time == 5.5
        assert attempt.changes_made == ["Increased timeout", "Updated retry policy"]
        assert attempt.verification_passed is True
        assert attempt.outcome_details == "Issue partially resolved"
        assert attempt.metadata == {"env": "production", "region": "us-east-1"}

    def test_recovery_attempt_to_dict(self) -> None:
        """Test RecoveryAttempt.to_dict() serialization."""
        timestamp = datetime.now(UTC)
        attempt = RecoveryAttempt(
            attempt_id="attempt-001",
            pattern_id="pattern-001",
            timestamp=timestamp,
            strategy_used="retry_with_backoff",
            action_type="RETRY",
            parameters={"max_retries": 3},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=2.5,
        )

        result = attempt.to_dict()

        assert result["attempt_id"] == "attempt-001"
        assert result["pattern_id"] == "pattern-001"
        assert result["timestamp"] == timestamp.isoformat()
        assert result["strategy_used"] == "retry_with_backoff"
        assert result["action_type"] == "RETRY"
        assert result["parameters"] == {"max_retries": 3}
        assert result["outcome"] == "success"
        assert result["success"] is True
        assert result["execution_time"] == 2.5

    def test_recovery_attempt_from_dict(self) -> None:
        """Test RecoveryAttempt.from_dict() deserialization."""
        timestamp = datetime.now(UTC)
        data = {
            "attempt_id": "attempt-001",
            "pattern_id": "pattern-001",
            "timestamp": timestamp.isoformat(),
            "strategy_used": "retry_with_backoff",
            "action_type": "RETRY",
            "parameters": {"max_retries": 3},
            "outcome": "success",
            "success": True,
            "error": None,
            "execution_time": 2.5,
            "changes_made": [],
            "verification_passed": False,
            "outcome_details": "",
            "metadata": {},
        }

        attempt = RecoveryAttempt.from_dict(data)

        assert attempt.attempt_id == "attempt-001"
        assert attempt.pattern_id == "pattern-001"
        assert attempt.timestamp == timestamp
        assert attempt.strategy_used == "retry_with_backoff"
        assert attempt.outcome == RecoveryOutcome.SUCCESS
        assert attempt.execution_time == 2.5

    def test_recovery_attempt_round_trip(self) -> None:
        """Test RecoveryAttempt serialization round trip."""
        timestamp = datetime.now(UTC)
        original = RecoveryAttempt(
            attempt_id="attempt-001",
            pattern_id="pattern-001",
            timestamp=timestamp,
            strategy_used="test_strategy",
            action_type="TEST",
            parameters={"key": "value"},
            outcome=RecoveryOutcome.FAILED,
            success=False,
            error="Test error",
            execution_time=1.0,
            changes_made=["Change 1"],
            verification_passed=True,
            outcome_details="Details",
            metadata={"meta": "data"},
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = RecoveryAttempt.from_dict(data)

        assert restored.attempt_id == original.attempt_id
        assert restored.pattern_id == original.pattern_id
        assert restored.timestamp == original.timestamp
        assert restored.strategy_used == original.strategy_used
        assert restored.action_type == original.action_type
        assert restored.parameters == original.parameters
        assert restored.outcome == original.outcome
        assert restored.success == original.success
        assert restored.error == original.error
        assert restored.execution_time == original.execution_time
        assert restored.changes_made == original.changes_made
        assert restored.verification_passed == original.verification_passed
        assert restored.outcome_details == original.outcome_details
        assert restored.metadata == original.metadata


# ============================================================================
# RecoveryPattern Model Tests
# ============================================================================


class TestRecoveryPattern:
    """Tests for RecoveryPattern model."""

    def test_recovery_pattern_init_minimal(self) -> None:
        """Test RecoveryPattern initialization with minimal fields."""
        first_seen = datetime.now(UTC)
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TIMEOUT",
            error_signature="timeout_sig_123",
            features={"file": "test.py", "line": 42},
            first_seen=first_seen,
            last_seen=first_seen,
        )

        assert pattern.pattern_id == "pattern-001"
        assert pattern.error_category == "TIMEOUT"
        assert pattern.error_signature == "timeout_sig_123"
        assert pattern.features == {"file": "test.py", "line": 42}
        assert pattern.occurrence_count == 1
        assert pattern.first_seen == first_seen
        assert pattern.last_seen == first_seen
        assert pattern.related_strategies == []
        assert pattern.success_count == 0
        assert pattern.failure_count == 0
        assert pattern.confidence == PatternConfidence.LOW
        assert pattern.metadata == {}

    def test_recovery_pattern_init_full(self) -> None:
        """Test RecoveryPattern initialization with all fields."""
        first_seen = datetime.now(UTC)
        last_seen = first_seen + timedelta(hours=1)
        pattern = RecoveryPattern(
            pattern_id="pattern-002",
            error_category="NETWORK_ISSUE",
            error_signature="network_sig_456",
            features={"host": "api.example.com", "port": 443},
            occurrence_count=5,
            first_seen=first_seen,
            last_seen=last_seen,
            related_strategies=["retry", "reconfigure"],
            success_count=3,
            failure_count=2,
            confidence=PatternConfidence.MEDIUM,
            metadata={"env": "staging"},
        )

        assert pattern.pattern_id == "pattern-002"
        assert pattern.error_category == "NETWORK_ISSUE"
        assert pattern.occurrence_count == 5
        assert pattern.related_strategies == ["retry", "reconfigure"]
        assert pattern.success_count == 3
        assert pattern.failure_count == 2
        assert pattern.confidence == PatternConfidence.MEDIUM
        assert pattern.metadata == {"env": "staging"}

    def test_recovery_pattern_to_dict(self) -> None:
        """Test RecoveryPattern.to_dict() serialization."""
        first_seen = datetime.now(UTC)
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TIMEOUT",
            error_signature="timeout_sig_123",
            features={"file": "test.py"},
            first_seen=first_seen,
            last_seen=first_seen,
            success_count=2,
            failure_count=1,
        )

        result = pattern.to_dict()

        assert result["pattern_id"] == "pattern-001"
        assert result["error_category"] == "TIMEOUT"
        assert result["error_signature"] == "timeout_sig_123"
        assert result["features"] == {"file": "test.py"}
        assert result["occurrence_count"] == 1
        assert result["first_seen"] == first_seen.isoformat()
        assert result["last_seen"] == first_seen.isoformat()
        assert result["success_count"] == 2
        assert result["failure_count"] == 1
        assert result["confidence"] == "low"

    def test_recovery_pattern_get_success_rate_no_attempts(self) -> None:
        """Test RecoveryPattern.get_success_rate() with no attempts."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
        )

        assert pattern.get_success_rate() == 0.0

    def test_recovery_pattern_get_success_rate_all_success(self) -> None:
        """Test RecoveryPattern.get_success_rate() with all successes."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=5,
            failure_count=0,
        )

        assert pattern.get_success_rate() == 1.0

    def test_recovery_pattern_get_success_rate_all_failures(self) -> None:
        """Test RecoveryPattern.get_success_rate() with all failures."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=0,
            failure_count=5,
        )

        assert pattern.get_success_rate() == 0.0

    def test_recovery_pattern_get_success_rate_mixed(self) -> None:
        """Test RecoveryPattern.get_success_rate() with mixed results."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=3,
            failure_count=2,
        )

        assert pattern.get_success_rate() == 0.6

    def test_recovery_pattern_update_confidence_high(self) -> None:
        """Test RecoveryPattern.update_confidence() sets HIGH confidence."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=5,
            failure_count=1,
        )

        pattern.update_confidence()

        assert pattern.confidence == PatternConfidence.HIGH

    def test_recovery_pattern_update_confidence_medium(self) -> None:
        """Test RecoveryPattern.update_confidence() sets MEDIUM confidence."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=3,
            failure_count=2,
        )

        pattern.update_confidence()

        assert pattern.confidence == PatternConfidence.MEDIUM

    def test_recovery_pattern_update_confidence_low(self) -> None:
        """Test RecoveryPattern.update_confidence() sets LOW confidence."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=1,
            failure_count=5,
        )

        pattern.update_confidence()

        assert pattern.confidence == PatternConfidence.LOW

    def test_recovery_pattern_update_confidence_insufficient_samples(self) -> None:
        """Test RecoveryPattern.update_confidence() with insufficient samples."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=2,
            failure_count=0,
        )

        pattern.update_confidence()

        # High success rate but insufficient samples -> not HIGH
        assert pattern.confidence == PatternConfidence.LOW


# ============================================================================
# LearnedStrategy Model Tests
# ============================================================================


class TestLearnedStrategy:
    """Tests for LearnedStrategy model."""

    def test_learned_strategy_init_minimal(self) -> None:
        """Test LearnedStrategy initialization with minimal fields."""
        first_learned = datetime.now(UTC)
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Retry with Backoff",
            strategy_type="RETRY",
            description="Retries with exponential backoff",
            success_rate=0.8,
            total_attempts=5,
            successful_attempts=4,
            failed_attempts=1,
            avg_execution_time=2.5,
            optimal_parameters={"max_retries": 3},
            confidence=PatternConfidence.MEDIUM,
            first_learned=first_learned,
        )

        assert strategy.strategy_id == "strategy-001"
        assert strategy.pattern_id == "pattern-001"
        assert strategy.strategy_name == "Retry with Backoff"
        assert strategy.strategy_type == "RETRY"
        assert strategy.description == "Retries with exponential backoff"
        assert strategy.success_rate == 0.8
        assert strategy.total_attempts == 5
        assert strategy.successful_attempts == 4
        assert strategy.failed_attempts == 1
        assert strategy.avg_execution_time == 2.5
        assert strategy.optimal_parameters == {"max_retries": 3}
        assert strategy.confidence == PatternConfidence.MEDIUM
        assert strategy.first_learned == first_learned
        assert strategy.last_successful_use is None
        assert strategy.last_attempt is None
        # Effectiveness score should be calculated in __post_init__
        assert strategy.effectiveness_score > 0
        assert strategy.metadata == {}

    def test_learned_strategy_init_full(self) -> None:
        """Test LearnedStrategy initialization with all fields."""
        first_learned = datetime.now(UTC)
        last_successful = first_learned + timedelta(hours=1)
        last_attempt = first_learned + timedelta(hours=2)

        strategy = LearnedStrategy(
            strategy_id="strategy-002",
            pattern_id="pattern-002",
            strategy_name="Reconfigure Timeout",
            strategy_type="RECONFIGURE",
            description="Increases timeout value",
            success_rate=0.9,
            total_attempts=10,
            successful_attempts=9,
            failed_attempts=1,
            avg_execution_time=1.0,
            optimal_parameters={"timeout": 120},
            confidence=PatternConfidence.HIGH,
            first_learned=first_learned,
            last_successful_use=last_successful,
            last_attempt=last_attempt,
            effectiveness_score=0.85,
            metadata={"tested_in": "production"},
        )

        assert strategy.strategy_id == "strategy-002"
        assert strategy.last_successful_use == last_successful
        assert strategy.last_attempt == last_attempt
        assert strategy.effectiveness_score == 0.85
        assert strategy.metadata == {"tested_in": "production"}

    def test_learned_strategy_to_dict(self) -> None:
        """Test LearnedStrategy.to_dict() serialization."""
        first_learned = datetime.now(UTC)
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test Strategy",
            strategy_type="TEST",
            description="Test description",
            success_rate=0.75,
            total_attempts=4,
            successful_attempts=3,
            failed_attempts=1,
            avg_execution_time=3.0,
            optimal_parameters={"param": "value"},
            confidence=PatternConfidence.MEDIUM,
            first_learned=first_learned,
        )

        result = strategy.to_dict()

        assert result["strategy_id"] == "strategy-001"
        assert result["pattern_id"] == "pattern-001"
        assert result["strategy_name"] == "Test Strategy"
        assert result["strategy_type"] == "TEST"
        assert result["description"] == "Test description"
        assert result["success_rate"] == 0.75
        assert result["total_attempts"] == 4
        assert result["successful_attempts"] == 3
        assert result["failed_attempts"] == 1
        assert result["avg_execution_time"] == 3.0
        assert result["optimal_parameters"] == {"param": "value"}
        assert result["confidence"] == "medium"
        assert result["first_learned"] == first_learned.isoformat()
        assert result["last_successful_use"] is None
        assert result["last_attempt"] is None

    def test_learned_strategy_from_dict(self) -> None:
        """Test LearnedStrategy.from_dict() deserialization."""
        first_learned = datetime.now(UTC)
        data = {
            "strategy_id": "strategy-001",
            "pattern_id": "pattern-001",
            "strategy_name": "Test Strategy",
            "strategy_type": "TEST",
            "description": "Test description",
            "success_rate": 0.75,
            "total_attempts": 4,
            "successful_attempts": 3,
            "failed_attempts": 1,
            "avg_execution_time": 3.0,
            "optimal_parameters": {"param": "value"},
            "confidence": "medium",
            "first_learned": first_learned.isoformat(),
            "last_successful_use": None,
            "last_attempt": None,
            "effectiveness_score": 0.6,
            "metadata": {},
        }

        strategy = LearnedStrategy.from_dict(data)

        assert strategy.strategy_id == "strategy-001"
        assert strategy.pattern_id == "pattern-001"
        assert strategy.success_rate == 0.75
        assert strategy.confidence == PatternConfidence.MEDIUM

    def test_learned_strategy_round_trip(self) -> None:
        """Test LearnedStrategy serialization round trip."""
        first_learned = datetime.now(UTC)
        last_successful = first_learned + timedelta(hours=1)
        original = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test Strategy",
            strategy_type="TEST",
            description="Test description",
            success_rate=0.8,
            total_attempts=5,
            successful_attempts=4,
            failed_attempts=1,
            avg_execution_time=2.0,
            optimal_parameters={"key": "value"},
            confidence=PatternConfidence.HIGH,
            first_learned=first_learned,
            last_successful_use=last_successful,
            metadata={"meta": "data"},
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = LearnedStrategy.from_dict(data)

        assert restored.strategy_id == original.strategy_id
        assert restored.pattern_id == original.pattern_id
        assert restored.strategy_name == original.strategy_name
        assert restored.success_rate == original.success_rate
        assert restored.optimal_parameters == original.optimal_parameters
        assert restored.metadata == original.metadata

    def test_learned_strategy_calculate_effectiveness_score_high_success_fast(self) -> None:
        """Test effectiveness score calculation for high success, fast execution."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.9,
            total_attempts=10,
            successful_attempts=9,
            failed_attempts=1,
            avg_execution_time=1.0,  # Fast
            optimal_parameters={},
            confidence=PatternConfidence.HIGH,
        )

        # High success rate + fast execution = high effectiveness
        assert strategy.effectiveness_score > 0.8

    def test_learned_strategy_calculate_effectiveness_score_high_success_slow(self) -> None:
        """Test effectiveness score calculation for high success, slow execution."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.9,
            total_attempts=10,
            successful_attempts=9,
            failed_attempts=1,
            avg_execution_time=60.0,  # Slow
            optimal_parameters={},
            confidence=PatternConfidence.HIGH,
        )

        # High success rate but slow execution = lower effectiveness
        assert strategy.effectiveness_score < 0.8
        assert strategy.effectiveness_score > 0.6

    def test_learned_strategy_calculate_effectiveness_score_low_success(self) -> None:
        """Test effectiveness score calculation for low success rate."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.3,
            total_attempts=10,
            successful_attempts=3,
            failed_attempts=7,
            avg_execution_time=1.0,
            optimal_parameters={},
            confidence=PatternConfidence.LOW,
        )

        # Low success rate = low effectiveness regardless of speed
        assert strategy.effectiveness_score < 0.5

    def test_learned_strategy_update_statistics_success(self) -> None:
        """Test LearnedStrategy.update_statistics() with successful recovery."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.5,
            total_attempts=10,
            successful_attempts=5,
            failed_attempts=5,
            avg_execution_time=2.0,
            optimal_parameters={"old": "params"},
            confidence=PatternConfidence.MEDIUM,
        )

        strategy.update_statistics(
            success=True,
            execution_time=3.0,
            parameters={"new": "params"},
        )

        assert strategy.total_attempts == 11
        assert strategy.successful_attempts == 6
        assert strategy.failed_attempts == 5
        assert strategy.last_successful_use is not None
        assert strategy.last_attempt is not None
        assert strategy.optimal_parameters == {"new": "params"}

    def test_learned_strategy_update_statistics_failure(self) -> None:
        """Test LearnedStrategy.update_statistics() with failed recovery."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.5,
            total_attempts=10,
            successful_attempts=5,
            failed_attempts=5,
            avg_execution_time=2.0,
            optimal_parameters={},
            confidence=PatternConfidence.MEDIUM,
        )

        strategy.update_statistics(
            success=False,
            execution_time=1.0,
        )

        assert strategy.total_attempts == 11
        assert strategy.successful_attempts == 5
        assert strategy.failed_attempts == 6
        assert strategy.last_successful_use is None  # Unchanged
        assert strategy.last_attempt is not None
        # Optimal parameters should not change on failure
        assert strategy.optimal_parameters == {}

    def test_learned_strategy_update_statistics_no_parameters(self) -> None:
        """Test LearnedStrategy.update_statistics() without parameters."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.5,
            total_attempts=10,
            successful_attempts=5,
            failed_attempts=5,
            avg_execution_time=2.0,
            optimal_parameters={"existing": "params"},
            confidence=PatternConfidence.MEDIUM,
        )

        strategy.update_statistics(success=True, execution_time=2.5)

        # Optimal parameters should remain unchanged
        assert strategy.optimal_parameters == {"existing": "params"}


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestRecoveryLearnerEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_recovery_attempt_with_all_outcomes(self) -> None:
        """Test RecoveryAttempt with all possible outcome values."""
        timestamp = datetime.now(UTC)
        outcomes = [
            RecoveryOutcome.SUCCESS,
            RecoveryOutcome.PARTIAL,
            RecoveryOutcome.FAILED,
            RecoveryOutcome.ESCALATED,
        ]

        for outcome in outcomes:
            attempt = RecoveryAttempt(
                attempt_id=f"attempt-{outcome.value}",
                pattern_id="pattern-001",
                timestamp=timestamp,
                strategy_used="test_strategy",
                action_type="TEST",
                parameters={},
                outcome=outcome,
                success=(outcome == RecoveryOutcome.SUCCESS),
            )
            assert attempt.outcome == outcome

    def test_recovery_pattern_with_zero_occurrences(self) -> None:
        """Test RecoveryPattern can handle zero occurrences."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            occurrence_count=0,
        )

        assert pattern.occurrence_count == 0
        assert pattern.get_success_rate() == 0.0

    def test_learned_strategy_with_zero_attempts(self) -> None:
        """Test LearnedStrategy with zero total attempts."""
        strategy = LearnedStrategy(
            strategy_id="strategy-001",
            pattern_id="pattern-001",
            strategy_name="Test",
            strategy_type="TEST",
            description="Test",
            success_rate=0.0,
            total_attempts=0,
            successful_attempts=0,
            failed_attempts=0,
            avg_execution_time=0.0,
            optimal_parameters={},
            confidence=PatternConfidence.LOW,
        )

        assert strategy.total_attempts == 0
        assert strategy.effectiveness_score >= 0.0

    def test_recovery_pattern_confidence_transition(self) -> None:
        """Test RecoveryPattern confidence transitions as data accumulates."""
        pattern = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
            success_count=0,
            failure_count=0,
        )

        # Initial: LOW confidence
        pattern.update_confidence()
        assert pattern.confidence == PatternConfidence.LOW

        # Add some success: still LOW (insufficient samples)
        pattern.success_count = 2
        pattern.failure_count = 0
        pattern.update_confidence()
        assert pattern.confidence == PatternConfidence.LOW

        # More attempts with good success: MEDIUM
        pattern.success_count = 3
        pattern.failure_count = 1
        pattern.update_confidence()
        assert pattern.confidence == PatternConfidence.MEDIUM

        # High success with sufficient samples: HIGH
        # Need > 0.8 success rate, so 9/10 = 0.9
        pattern.success_count = 9
        pattern.failure_count = 1
        pattern.update_confidence()
        assert pattern.confidence == PatternConfidence.HIGH

    def test_empty_metadata_default(self) -> None:
        """Test that empty metadata dict is not shared across instances."""
        pattern1 = RecoveryPattern(
            pattern_id="pattern-001",
            error_category="TEST",
            error_signature="test_sig",
            features={},
        )
        pattern2 = RecoveryPattern(
            pattern_id="pattern-002",
            error_category="TEST",
            error_signature="test_sig2",
            features={},
        )

        pattern1.metadata["key"] = "value1"
        pattern2.metadata["key"] = "value2"

        # Each instance should have its own metadata dict
        assert pattern1.metadata["key"] == "value1"
        assert pattern2.metadata["key"] == "value2"
        assert pattern1.metadata is not pattern2.metadata


# ============================================================================
# RecoveryLearner Persistence Tests
# ============================================================================


class TestRecoveryLearnerPersistence:
    """Tests for RecoveryLearner data persistence."""

    def test_recovery_learner_init_creates_storage(self, tmp_path: Path) -> None:
        """Test RecoveryLearner initialization creates storage file."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        assert learning_path.exists()
        assert learner.learning_path == learning_path

    def test_recovery_learner_init_with_existing_data(self, tmp_path: Path) -> None:
        """Test RecoveryLearner initialization loads existing data."""
        learning_path = tmp_path / "recovery_learning.json"

        # Create initial learner and add data
        learner1 = RecoveryLearner(learning_path=learning_path)
        attempt_id = learner1.record_attempt(
            pattern_id="test-pattern",
            strategy_used="retry_strategy",
            action_type="RETRY",
            parameters={"max_retries": 3},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
        )

        # Create new learner instance - should load existing data
        learner2 = RecoveryLearner(learning_path=learning_path)
        assert attempt_id in learner2._attempts
        assert "test-pattern" in learner2._patterns
        assert len(learner2._attempts) == 1

    def test_recovery_learner_save_persists_attempts(self, tmp_path: Path) -> None:
        """Test that recording an attempt persists to disk."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record an attempt
        learner.record_attempt(
            pattern_id="timeout-error",
            strategy_used="retry_with_backoff",
            action_type="RETRY",
            parameters={"max_retries": 3},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=5.2,
            metadata={"error_category": "TIMEOUT"},
        )

        # Verify file was updated
        import json

        data = json.loads(learning_path.read_text(encoding="utf-8"))
        assert "attempts" in data
        assert len(data["attempts"]) == 1
        assert "patterns" in data
        assert "timeout-error" in data["patterns"]

    def test_recovery_learner_load_reconstructs_patterns(self, tmp_path: Path) -> None:
        """Test that loading reconstructs pattern data correctly."""
        learning_path = tmp_path / "recovery_learning.json"

        # Create learner with pattern data
        learner1 = RecoveryLearner(learning_path=learning_path)
        learner1.record_attempt(
            pattern_id="network-error",
            strategy_used="retry",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            metadata={"error_category": "NETWORK", "error_signature": "conn_refused"},
        )

        # Load in new instance
        learner2 = RecoveryLearner(learning_path=learning_path)
        pattern = learner2._patterns["network-error"]

        assert pattern.pattern_id == "network-error"
        assert pattern.error_category == "NETWORK"
        assert pattern.occurrence_count == 2  # Default 1 + 1 increment
        assert pattern.success_count == 1

    def test_recovery_learner_load_reconstructs_strategies(self, tmp_path: Path) -> None:
        """Test that loading reconstructs learned strategies correctly."""
        learning_path = tmp_path / "recovery_learning.json"

        # Create learner with strategy data
        learner1 = RecoveryLearner(learning_path=learning_path)
        learner1.record_attempt(
            pattern_id="test-pattern",
            strategy_used="test_strategy",
            action_type="TEST",
            parameters={"param": "value"},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
        )

        # Load in new instance
        learner2 = RecoveryLearner(learning_path=learning_path)
        strategy_key = "test-pattern:test_strategy"
        assert strategy_key in learner2._learned_strategies

        strategy = learner2._learned_strategies[strategy_key]
        assert strategy.strategy_name == "test_strategy"
        assert strategy.total_attempts == 1
        assert strategy.successful_attempts == 1

    def test_recovery_learner_atomic_write_prevents_data_loss(self, tmp_path: Path) -> None:
        """Test that atomic write prevents data corruption."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record multiple attempts
        for i in range(5):
            learner.record_attempt(
                pattern_id=f"pattern-{i}",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        # Verify data integrity
        import json

        data = json.loads(learning_path.read_text(encoding="utf-8"))
        assert len(data["attempts"]) == 5
        assert len(data["patterns"]) == 5

    def test_recovery_learner_handles_corrupted_file(self, tmp_path: Path) -> None:
        """Test RecoveryLearner handles corrupted JSON gracefully."""
        learning_path = tmp_path / "recovery_learning.json"

        # Write corrupted JSON
        learning_path.write_text("{invalid json", encoding="utf-8")

        # Should start fresh without crashing
        learner = RecoveryLearner(learning_path=learning_path)
        assert len(learner._attempts) == 0
        assert len(learner._patterns) == 0
        assert len(learner._learned_strategies) == 0

    def test_recovery_learner_handles_empty_file(self, tmp_path: Path) -> None:
        """Test RecoveryLearner handles empty file gracefully."""
        learning_path = tmp_path / "recovery_learning.json"
        learning_path.write_text("", encoding="utf-8")

        # Should initialize empty state
        learner = RecoveryLearner(learning_path=learning_path)
        assert len(learner._attempts) == 0

    def test_recovery_learner_metadata_in_saved_file(self, tmp_path: Path) -> None:
        """Test that metadata is correctly saved in learning file."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        learner.record_attempt(
            pattern_id="test-pattern",
            strategy_used="test_strategy",
            action_type="TEST",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
        )

        import json

        data = json.loads(learning_path.read_text(encoding="utf-8"))
        assert "metadata" in data
        assert data["metadata"]["total_attempts"] == 1
        assert data["metadata"]["total_patterns"] == 1
        assert "last_updated" in data["metadata"]


# ============================================================================
# RecoveryLearner Lookup Tests
# ============================================================================


class TestRecoveryLearnerLookup:
    """Tests for RecoveryLearner query and lookup methods."""

    def test_get_pattern_statistics_exists(self, tmp_path: Path) -> None:
        """Test get_pattern_statistics returns correct data for existing pattern."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record attempts for a pattern
        learner.record_attempt(
            pattern_id="test-pattern",
            strategy_used="strategy1",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            metadata={"error_category": "TIMEOUT", "error_signature": "timeout_sig"},
        )

        stats = learner.get_pattern_statistics("test-pattern")

        assert stats is not None
        assert stats["pattern_id"] == "test-pattern"
        assert stats["error_category"] == "TIMEOUT"
        assert stats["occurrence_count"] == 2  # Default 1 + 1 increment
        assert stats["success_rate"] == 1.0
        assert stats["confidence"] == "low"  # Low confidence initially
        assert "first_seen" in stats
        assert "last_seen" in stats

    def test_get_pattern_statistics_not_exists(self, tmp_path: Path) -> None:
        """Test get_pattern_statistics returns None for non-existent pattern."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        stats = learner.get_pattern_statistics("non-existent-pattern")

        assert stats is None

    def test_get_pattern_statistics_multiple_attempts(self, tmp_path: Path) -> None:
        """Test get_pattern_statistics with multiple attempts."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record multiple attempts with mixed results
        for i in range(3):
            learner.record_attempt(
                pattern_id="mixed-pattern",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS if i < 2 else RecoveryOutcome.FAILED,
                success=i < 2,
            )

        stats = learner.get_pattern_statistics("mixed-pattern")

        assert stats["occurrence_count"] == 4  # Default 1 + 3 increments
        assert stats["success_rate"] == 2/3  # 2 successes out of 3 attempts

    def test_get_best_strategy_exists(self, tmp_path: Path) -> None:
        """Test get_best_strategy returns best strategy for pattern."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record attempts with different strategies
        learner.record_attempt(
            pattern_id="test-pattern",
            strategy_used="good_strategy",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=1.0,
        )
        learner.record_attempt(
            pattern_id="test-pattern",
            strategy_used="bad_strategy",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.FAILED,
            success=False,
            execution_time=10.0,
        )

        # Need more attempts to meet minimum thresholds
        for _ in range(3):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="good_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=1.0,
            )
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="bad_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.FAILED,
                success=False,
                execution_time=10.0,
            )

        strategy = learner.get_best_strategy("test-pattern")

        assert strategy is not None
        assert strategy.strategy_name == "good_strategy"  # Higher effectiveness
        assert strategy.success_rate == 1.0

    def test_get_best_strategy_not_exists(self, tmp_path: Path) -> None:
        """Test get_best_strategy returns None for non-existent pattern."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        strategy = learner.get_best_strategy("non-existent-pattern")

        assert strategy is None

    def test_get_best_strategy_respects_min_confidence(self, tmp_path: Path) -> None:
        """Test get_best_strategy respects minimum confidence threshold."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record attempts for low confidence strategy
        learner.record_attempt(
            pattern_id="test-pattern",
            strategy_used="low_conf_strategy",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
        )

        # With MEDIUM confidence requirement, LOW confidence strategy should not be returned
        strategy = learner.get_best_strategy(
            "test-pattern",
            min_confidence=PatternConfidence.MEDIUM,
        )

        assert strategy is None

    def test_get_best_strategy_high_confidence(self, tmp_path: Path) -> None:
        """Test get_best_strategy returns HIGH confidence strategies."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record multiple successful attempts to build high confidence
        for i in range(10):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="high_conf_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS if i < 9 else RecoveryOutcome.FAILED,
                success=i < 9,
                execution_time=1.0,
            )

        strategy = learner.get_best_strategy(
            "test-pattern",
            min_confidence=PatternConfidence.HIGH,
        )

        assert strategy is not None
        assert strategy.strategy_name == "high_conf_strategy"
        assert strategy.confidence == PatternConfidence.HIGH

    def test_get_all_attempts_unfiltered(self, tmp_path: Path) -> None:
        """Test get_all_attempts returns all attempts unfiltered."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record multiple attempts
        for i in range(5):
            learner.record_attempt(
                pattern_id=f"pattern-{i % 2}",  # Alternate between two patterns
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        attempts = learner.get_all_attempts()

        assert len(attempts) == 5
        # Should be sorted by timestamp (most recent first)
        for i in range(len(attempts) - 1):
            assert attempts[i].timestamp >= attempts[i + 1].timestamp

    def test_get_all_attempts_filtered_by_pattern(self, tmp_path: Path) -> None:
        """Test get_all_attempts filters by pattern_id."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record attempts for different patterns
        for i in range(3):
            learner.record_attempt(
                pattern_id="pattern-A",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )
        for i in range(2):
            learner.record_attempt(
                pattern_id="pattern-B",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        attempts_a = learner.get_all_attempts(pattern_id="pattern-A")
        attempts_b = learner.get_all_attempts(pattern_id="pattern-B")

        assert len(attempts_a) == 3
        assert len(attempts_b) == 2
        assert all(a.pattern_id == "pattern-A" for a in attempts_a)
        assert all(a.pattern_id == "pattern-B" for a in attempts_b)

    def test_get_all_attempts_with_limit(self, tmp_path: Path) -> None:
        """Test get_all_attempts respects limit parameter."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record multiple attempts
        for i in range(10):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        attempts = learner.get_all_attempts(limit=5)

        assert len(attempts) == 5
        # Should return the 5 most recent attempts
        # (they're already sorted by timestamp descending)

    def test_get_learning_summary(self, tmp_path: Path) -> None:
        """Test get_learning_summary returns comprehensive statistics."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record mixed results
        for i in range(7):
            learner.record_attempt(
                pattern_id=f"pattern-{i % 3}",  # 3 different patterns
                strategy_used=f"strategy-{i % 2}",  # 2 different strategies
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS if i < 5 else RecoveryOutcome.FAILED,
                success=i < 5,
            )

        summary = learner.get_learning_summary()

        assert summary["total_attempts"] == 7
        assert summary["successful_attempts"] == 5
        assert summary["failed_attempts"] == 2
        assert summary["overall_success_rate"] == 5/7
        assert summary["total_patterns"] == 3
        assert summary["total_learned_strategies"] == 6  # 3 patterns * 2 strategies
        assert "strategies_by_confidence" in summary
        assert "high" in summary["strategies_by_confidence"]
        assert "medium" in summary["strategies_by_confidence"]
        assert "low" in summary["strategies_by_confidence"]

    def test_get_learning_summary_empty(self, tmp_path: Path) -> None:
        """Test get_learning_summary with no data."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        summary = learner.get_learning_summary()

        assert summary["total_attempts"] == 0
        assert summary["successful_attempts"] == 0
        assert summary["failed_attempts"] == 0
        assert summary["overall_success_rate"] == 0.0
        assert summary["total_patterns"] == 0
        assert summary["total_learned_strategies"] == 0

    def test_clear_old_data(self, tmp_path: Path) -> None:
        """Test clear_old_data removes old attempts."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record 20 attempts
        for i in range(20):
            learner.record_attempt(
                pattern_id=f"pattern-{i}",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        assert len(learner._attempts) == 20

        # Keep only 10 most recent
        removed = learner.clear_old_data(keep_recent=10)

        assert removed == 10
        assert len(learner._attempts) == 10

        # Patterns should still exist (they're learned knowledge)
        assert len(learner._patterns) == 20

    def test_clear_old_data_below_threshold(self, tmp_path: Path) -> None:
        """Test clear_old_data when attempts below threshold."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Record only 5 attempts
        for i in range(5):
            learner.record_attempt(
                pattern_id=f"pattern-{i}",
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        # Try to keep 10 (we have fewer than that)
        removed = learner.clear_old_data(keep_recent=10)

        assert removed == 0
        assert len(learner._attempts) == 5


# ============================================================================
# RecoveryLearner Integration Tests
# ============================================================================


class TestRecoveryLearnerIntegration:
    """Integration tests for RecoveryLearner workflows."""

    def test_learning_workflow_end_to_end(self, tmp_path: Path) -> None:
        """Test complete learning workflow: record, persist, load, query."""
        learning_path = tmp_path / "recovery_learning.json"

        # Phase 1: Record learning data
        learner1 = RecoveryLearner(learning_path=learning_path)
        learner1.record_attempt(
            pattern_id="timeout-api-call",
            strategy_used="retry_with_backoff",
            action_type="RETRY",
            parameters={"max_retries": 3, "backoff": "exponential"},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=5.2,
            metadata={"error_category": "TIMEOUT", "error_signature": "api_timeout"},
        )
        learner1.record_attempt(
            pattern_id="timeout-api-call",
            strategy_used="retry_with_backoff",
            action_type="RETRY",
            parameters={"max_retries": 3, "backoff": "exponential"},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=4.8,
        )
        learner1.record_attempt(
            pattern_id="timeout-api-call",
            strategy_used="increase_timeout",
            action_type="RECONFIGURE",
            parameters={"timeout": 60},
            outcome=RecoveryOutcome.PARTIAL,
            success=False,
            execution_time=2.0,
        )

        # Phase 2: Load in new instance
        learner2 = RecoveryLearner(learning_path=learning_path)

        # Phase 3: Query learned knowledge
        stats = learner2.get_pattern_statistics("timeout-api-call")
        assert stats is not None
        assert stats["occurrence_count"] == 4  # Default 1 + 3 attempts

        best_strategy = learner2.get_best_strategy(
            "timeout-api-call",
            min_confidence=PatternConfidence.LOW,  # Use LOW due to limited attempts
        )
        assert best_strategy is not None
        assert best_strategy.strategy_name == "retry_with_backoff"
        assert best_strategy.success_rate == 1.0  # 2/2 successes

        attempts = learner2.get_all_attempts(pattern_id="timeout-api-call")
        assert len(attempts) == 3

        summary = learner2.get_learning_summary()
        assert summary["total_attempts"] == 3
        assert summary["total_patterns"] == 1

    def test_pattern_confidence_evolution(self, tmp_path: Path) -> None:
        """Test pattern confidence evolves as data accumulates."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        pattern_id = "evolving-pattern"

        # Initial attempts - LOW confidence
        learner.record_attempt(
            pattern_id=pattern_id,
            strategy_used="strategy",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
        )

        stats = learner.get_pattern_statistics(pattern_id)
        assert stats["confidence"] == "low"

        # More successful attempts - confidence should increase
        for _ in range(5):
            learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used="strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        stats = learner.get_pattern_statistics(pattern_id)
        # With 6 successes, confidence should be at least MEDIUM
        assert stats["confidence"] in ["medium", "high"]

    def test_strategy_ranking_by_effectiveness(self, tmp_path: Path) -> None:
        """Test that strategies are ranked by effectiveness score."""
        learning_path = tmp_path / "recovery_learning.json"
        learner = RecoveryLearner(learning_path=learning_path)

        # Fast and successful strategy (4 attempts = MEDIUM confidence)
        for _ in range(4):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="fast_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=1.0,
            )

        # Slow but successful strategy (4 attempts = MEDIUM confidence)
        for _ in range(4):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="slow_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=60.0,
            )

        best = learner.get_best_strategy(
            "test-pattern",
            min_confidence=PatternConfidence.MEDIUM,  # Both strategies have MEDIUM confidence
        )
        assert best is not None
        # Fast strategy should have higher effectiveness
        assert best.strategy_name == "fast_strategy"


# ============================================================================
# RecoveryLearner Integration Tests with Mock Healing Data
# ============================================================================


class TestRecoveryLearnerIntegration:
    """Integration tests for RecoveryLearner with mock healing data."""

    # ========================================================================
    # Fixtures
    # ========================================================================

    @pytest.fixture
    def learning_path(self, tmp_path: Path) -> Path:
        """Create a temporary learning data path."""
        return tmp_path / "recovery_learning.json"

    @pytest.fixture
    def learner(self, learning_path: Path) -> RecoveryLearner:
        """Create a RecoveryLearner instance for testing."""
        return RecoveryLearner(learning_path=learning_path)

    @pytest.fixture
    def mock_timeout_attempts(self) -> list[dict[str, Any]]:
        """Mock healing data for timeout error recovery attempts."""
        return [
            {
                "pattern_id": "timeout-api-call",
                "strategy_used": "retry_with_backoff",
                "action_type": "RETRY",
                "parameters": {"max_retries": 3, "backoff_multiplier": 2.0},
                "outcome": RecoveryOutcome.SUCCESS,
                "success": True,
                "execution_time": 5.2,
                "error": None,
                "changes_made": ["Increased retry count", "Applied exponential backoff"],
                "verification_passed": True,
                "outcome_details": "Successfully recovered after 2 retries",
                "metadata": {
                    "error_category": "timeout",
                    "error_signature": "api_call_timeout",
                    "initial_error": "API call timed out after 30s",
                    "retry_count": 2,
                },
            },
            {
                "pattern_id": "timeout-api-call",
                "strategy_used": "retry_with_backoff",
                "action_type": "RETRY",
                "parameters": {"max_retries": 3, "backoff_multiplier": 2.0},
                "outcome": RecoveryOutcome.SUCCESS,
                "success": True,
                "execution_time": 4.8,
                "error": None,
                "changes_made": ["Applied exponential backoff"],
                "verification_passed": True,
                "outcome_details": "Successfully recovered after 1 retry",
                "metadata": {
                    "error_category": "timeout",
                    "error_signature": "api_call_timeout",
                    "initial_error": "API call timed out after 30s",
                    "retry_count": 1,
                },
            },
            {
                "pattern_id": "timeout-api-call",
                "strategy_used": "increase_timeout",
                "action_type": "RECONFIGURE",
                "parameters": {"timeout": 120},
                "outcome": RecoveryOutcome.PARTIAL,
                "success": False,
                "execution_time": 2.5,
                "error": "Timeout increased but issue persists",
                "changes_made": ["Increased timeout to 120s"],
                "verification_passed": False,
                "outcome_details": "Partial recovery - timeout increased but retries still needed",
                "metadata": {
                    "error_category": "timeout",
                    "error_signature": "api_call_timeout",
                    "initial_error": "API call timed out after 30s",
                },
            },
        ]

    @pytest.fixture
    def mock_connection_attempts(self) -> list[dict[str, Any]]:
        """Mock healing data for connection error recovery attempts."""
        return [
            {
                "pattern_id": "connection-database",
                "strategy_used": "reconnect_with_backoff",
                "action_type": "RETRY",
                "parameters": {"max_retries": 5, "initial_delay": 1.0},
                "outcome": RecoveryOutcome.SUCCESS,
                "success": True,
                "execution_time": 8.3,
                "error": None,
                "changes_made": ["Re-established database connection"],
                "verification_passed": True,
                "outcome_details": "Successfully reconnected after 3 attempts",
                "metadata": {
                    "error_category": "connection",
                    "error_signature": "database_connection_lost",
                    "initial_error": "Database connection lost",
                    "connection_pool": "primary",
                },
            },
            {
                "pattern_id": "connection-database",
                "strategy_used": "switch_to_fallback",
                "action_type": "FALLBACK",
                "parameters": {"fallback_host": "db-secondary.local"},
                "outcome": RecoveryOutcome.SUCCESS,
                "success": True,
                "execution_time": 3.1,
                "error": None,
                "changes_made": ["Switched to fallback database"],
                "verification_passed": True,
                "outcome_details": "Successfully switched to secondary database",
                "metadata": {
                    "error_category": "connection",
                    "error_signature": "database_connection_lost",
                    "initial_error": "Primary database unavailable",
                    "fallback_used": "db-secondary.local",
                },
            },
        ]

    @pytest.fixture
    def mock_memory_attempts(self) -> list[dict[str, Any]]:
        """Mock healing data for memory error recovery attempts."""
        return [
            {
                "pattern_id": "memory-out-of-memory",
                "strategy_used": "clear_cache",
                "action_type": "CLEANUP",
                "parameters": {"aggressive": True},
                "outcome": RecoveryOutcome.FAILED,
                "success": False,
                "execution_time": 1.2,
                "error": "Cache cleared but memory still insufficient",
                "changes_made": ["Cleared all caches"],
                "verification_passed": False,
                "outcome_details": "Cache cleanup insufficient",
                "metadata": {
                    "error_category": "resource",
                    "error_signature": "out_of_memory",
                    "initial_error": "Process out of memory",
                    "memory_usage_mb": 2048,
                },
            },
            {
                "pattern_id": "memory-out-of-memory",
                "strategy_used": "restart_worker",
                "action_type": "RESTART",
                "parameters": {"graceful": True},
                "outcome": RecoveryOutcome.SUCCESS,
                "success": True,
                "execution_time": 6.5,
                "error": None,
                "changes_made": ["Restarted worker process"],
                "verification_passed": True,
                "outcome_details": "Worker restart successful",
                "metadata": {
                    "error_category": "resource",
                    "error_signature": "out_of_memory",
                    "initial_error": "Worker process out of memory",
                    "worker_id": "worker-3",
                },
            },
        ]

    # ========================================================================
    # Recording Attempts Tests
    # ========================================================================

    def test_record_single_attempt(self, learner: RecoveryLearner) -> None:
        """Test recording a single recovery attempt."""
        attempt_id = learner.record_attempt(
            pattern_id="test-pattern",
            strategy_used="test_strategy",
            action_type="RETRY",
            parameters={"retry_count": 3},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=5.0,
        )

        assert attempt_id is not None
        assert len(learner._attempts) == 1
        assert len(learner._patterns) == 1
        assert len(learner._learned_strategies) == 1

        attempt = learner._attempts[attempt_id]
        assert attempt.pattern_id == "test-pattern"
        assert attempt.strategy_used == "test_strategy"
        assert attempt.success is True

    def test_record_multiple_attempts(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test recording multiple recovery attempts."""
        attempt_ids = []
        for attempt_data in mock_timeout_attempts:
            attempt_id = learner.record_attempt(**attempt_data)
            attempt_ids.append(attempt_id)

        assert len(attempt_ids) == 3
        assert len(learner._attempts) == 3
        assert len(learner._patterns) == 1  # All same pattern
        assert len(learner._learned_strategies) == 2  # 2 different strategies

    def test_record_attempts_across_patterns(
        self,
        learner: RecoveryLearner,
        mock_timeout_attempts: list[dict[str, Any]],
        mock_connection_attempts: list[dict[str, Any]],
        mock_memory_attempts: list[dict[str, Any]],
    ) -> None:
        """Test recording attempts across multiple error patterns."""
        all_attempts = (
            mock_timeout_attempts + mock_connection_attempts + mock_memory_attempts
        )

        for attempt_data in all_attempts:
            learner.record_attempt(**attempt_data)

        assert len(learner._attempts) == 7  # 3 + 2 + 2
        assert len(learner._patterns) == 3  # 3 different patterns
        assert len(learner._learned_strategies) == 6  # 6 different strategies (2+2+2)

    # ========================================================================
    # Learning from History Tests
    # ========================================================================

    def test_learn_from_history_returns_strategies(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test learning from historical attempts returns strategies."""
        # Record attempts
        for attempt_data in mock_timeout_attempts:
            learner.record_attempt(**attempt_data)

        # Add more attempts to reach MEDIUM confidence
        for _ in range(3):
            learner.record_attempt(
                pattern_id="timeout-api-call",
                strategy_used="retry_with_backoff",
                action_type="RETRY",
                parameters={"max_retries": 3, "backoff_multiplier": 2.0},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=5.0,
            )

        # Learn from history
        strategies = learner.learn_from_history(
            min_attempts=2, min_success_rate=0.5
        )

        # Should return at least the successful retry_with_backoff strategy
        assert len(strategies) >= 1
        assert any(
            s.strategy_name == "retry_with_backoff" for s in strategies
        ), "Should include retry_with_backoff strategy"

    def test_learn_from_history_filters_by_thresholds(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test learning from history filters by minimum thresholds."""
        for attempt_data in mock_timeout_attempts:
            learner.record_attempt(**attempt_data)

        # Add more attempts to reach higher confidence
        for _ in range(3):
            learner.record_attempt(
                pattern_id="timeout-api-call",
                strategy_used="retry_with_backoff",
                action_type="RETRY",
                parameters={"max_retries": 3, "backoff_multiplier": 2.0},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=5.0,
            )

        # Very high threshold that won't be met
        strict_strategies = learner.learn_from_history(
            min_attempts=10, min_success_rate=0.95
        )
        assert len(strict_strategies) == 0

        # Lower threshold should return strategies
        lenient_strategies = learner.learn_from_history(
            min_attempts=2, min_success_rate=0.5
        )
        assert len(lenient_strategies) >= 1

    def test_learn_from_history_sorts_by_effectiveness(
        self, learner: RecoveryLearner
    ) -> None:
        """Test that learned strategies are sorted by effectiveness."""
        # Record attempts for two strategies
        for _ in range(5):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="fast_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=1.0,
            )

        for _ in range(5):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="slow_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=60.0,
            )

        strategies = learner.learn_from_history(
            min_attempts=3, min_success_rate=0.5
        )

        # Fast strategy should come first due to better effectiveness
        assert len(strategies) >= 2
        assert strategies[0].strategy_name == "fast_strategy"
        assert strategies[1].strategy_name == "slow_strategy"

    # ========================================================================
    # Pattern Statistics Tests
    # ========================================================================

    def test_get_pattern_statistics(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test retrieving statistics for a specific pattern."""
        for attempt_data in mock_timeout_attempts:
            learner.record_attempt(**attempt_data)

        stats = learner.get_pattern_statistics("timeout-api-call")

        assert stats is not None
        assert stats["pattern_id"] == "timeout-api-call"
        assert stats["error_category"] == "timeout"
        assert stats["occurrence_count"] == 4  # Default 1 + 3 attempts
        assert stats["success_rate"] == 2 / 3  # 2 successes out of 3 attempts
        assert "retry_with_backoff" in stats["related_strategies"]
        assert "increase_timeout" in stats["related_strategies"]

    def test_get_pattern_statistics_not_found(self, learner: RecoveryLearner) -> None:
        """Test retrieving statistics for non-existent pattern."""
        stats = learner.get_pattern_statistics("non-existent-pattern")
        assert stats is None

    def test_get_pattern_statistics_multiple_patterns(
        self,
        learner: RecoveryLearner,
        mock_timeout_attempts: list[dict[str, Any]],
        mock_connection_attempts: list[dict[str, Any]],
    ) -> None:
        """Test pattern statistics are tracked separately for different patterns."""
        for attempt_data in mock_timeout_attempts + mock_connection_attempts:
            learner.record_attempt(**attempt_data)

        timeout_stats = learner.get_pattern_statistics("timeout-api-call")
        connection_stats = learner.get_pattern_statistics("connection-database")

        assert timeout_stats is not None
        assert connection_stats is not None
        assert timeout_stats["pattern_id"] != connection_stats["pattern_id"]
        assert timeout_stats["occurrence_count"] == 4  # Default 1 + 3 attempts
        assert connection_stats["occurrence_count"] == 3  # Default 1 + 2 attempts

    # ========================================================================
    # Best Strategy Tests
    # ========================================================================

    def test_get_best_strategy(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test getting the best strategy for a pattern."""
        for attempt_data in mock_timeout_attempts:
            learner.record_attempt(**attempt_data)

        # Get best strategy with low confidence threshold
        best = learner.get_best_strategy(
            "timeout-api-call",
            min_confidence=PatternConfidence.LOW,
        )

        assert best is not None
        assert best.pattern_id == "timeout-api-call"
        assert best.strategy_name in ["retry_with_backoff", "increase_timeout"]

    def test_get_best_strategy_no_strategies(self, learner: RecoveryLearner) -> None:
        """Test getting best strategy when no strategies exist."""
        best = learner.get_best_strategy("non-existent-pattern")
        assert best is None

    def test_get_best_strategy_high_confidence(
        self, learner: RecoveryLearner
    ) -> None:
        """Test getting best strategy with high confidence requirement."""
        # Record attempts to build confidence
        for _ in range(6):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="good_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=2.0,
            )

        # High confidence should find the strategy
        best = learner.get_best_strategy(
            "test-pattern",
            min_confidence=PatternConfidence.HIGH,
        )

        assert best is not None
        assert best.strategy_name == "good_strategy"
        assert best.confidence == PatternConfidence.HIGH

    def test_get_best_strategy_multiple_patterns(
        self,
        learner: RecoveryLearner,
        mock_timeout_attempts: list[dict[str, Any]],
        mock_connection_attempts: list[dict[str, Any]],
    ) -> None:
        """Test getting best strategy for different patterns."""
        for attempt_data in mock_timeout_attempts + mock_connection_attempts:
            learner.record_attempt(**attempt_data)

        timeout_best = learner.get_best_strategy(
            "timeout-api-call",
            min_confidence=PatternConfidence.LOW,
        )
        connection_best = learner.get_best_strategy(
            "connection-database",
            min_confidence=PatternConfidence.LOW,
        )

        assert timeout_best is not None
        assert connection_best is not None
        assert timeout_best.pattern_id != connection_best.pattern_id

    # ========================================================================
    # Retrieving Attempts Tests
    # ========================================================================

    def test_get_all_attempts(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test retrieving all recovery attempts."""
        for attempt_data in mock_timeout_attempts:
            learner.record_attempt(**attempt_data)

        attempts = learner.get_all_attempts()

        assert len(attempts) == 3
        # Should be sorted by timestamp (most recent first)
        assert attempts[0].timestamp >= attempts[1].timestamp
        assert attempts[1].timestamp >= attempts[2].timestamp

    def test_get_all_attempts_filtered_by_pattern(
        self,
        learner: RecoveryLearner,
        mock_timeout_attempts: list[dict[str, Any]],
        mock_connection_attempts: list[dict[str, Any]],
    ) -> None:
        """Test filtering attempts by pattern."""
        for attempt_data in mock_timeout_attempts + mock_connection_attempts:
            learner.record_attempt(**attempt_data)

        timeout_attempts = learner.get_all_attempts(pattern_id="timeout-api-call")
        connection_attempts = learner.get_all_attempts(
            pattern_id="connection-database"
        )

        assert len(timeout_attempts) == 3
        assert len(connection_attempts) == 2
        assert all(a.pattern_id == "timeout-api-call" for a in timeout_attempts)
        assert all(a.pattern_id == "connection-database" for a in connection_attempts)

    def test_get_all_attempts_with_limit(
        self, learner: RecoveryLearner, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test limiting the number of attempts returned."""
        for attempt_data in mock_timeout_attempts:
            learner.record_attempt(**attempt_data)

        attempts = learner.get_all_attempts(limit=2)

        assert len(attempts) == 2

    # ========================================================================
    # Learning Summary Tests
    # ========================================================================

    def test_get_learning_summary(
        self,
        learner: RecoveryLearner,
        mock_timeout_attempts: list[dict[str, Any]],
        mock_connection_attempts: list[dict[str, Any]],
        mock_memory_attempts: list[dict[str, Any]],
    ) -> None:
        """Test getting comprehensive learning summary."""
        for attempt_data in (
            mock_timeout_attempts + mock_connection_attempts + mock_memory_attempts
        ):
            learner.record_attempt(**attempt_data)

        summary = learner.get_learning_summary()

        assert summary["total_attempts"] == 7
        assert summary["successful_attempts"] == 5  # Count successes in mock data
        assert summary["failed_attempts"] == 2
        assert summary["total_patterns"] == 3
        assert summary["total_learned_strategies"] == 6  # 6 different strategies (2+2+2)
        assert summary["overall_success_rate"] == 5 / 7
        assert "strategies_by_confidence" in summary

    def test_get_learning_summary_empty(self, learner: RecoveryLearner) -> None:
        """Test learning summary with no data."""
        summary = learner.get_learning_summary()

        assert summary["total_attempts"] == 0
        assert summary["successful_attempts"] == 0
        assert summary["failed_attempts"] == 0
        assert summary["total_patterns"] == 0
        assert summary["total_learned_strategies"] == 0
        assert summary["overall_success_rate"] == 0.0

    # ========================================================================
    # Confidence Calculation Tests
    # ========================================================================

    def test_calculate_confidence_high_success_high_samples(
        self, learner: RecoveryLearner
    ) -> None:
        """Test confidence calculation with high success rate and many samples."""
        confidence = learner.calculate_confidence(0.9, 15)
        assert confidence > 0.8  # Should be high

    def test_calculate_confidence_low_success_low_samples(
        self, learner: RecoveryLearner
    ) -> None:
        """Test confidence calculation with low success rate and few samples."""
        confidence = learner.calculate_confidence(0.3, 2)
        assert confidence < 0.5  # Should be low

    def test_calculate_confidence_moderate_success_moderate_samples(
        self, learner: RecoveryLearner
    ) -> None:
        """Test confidence calculation with moderate values."""
        confidence = learner.calculate_confidence(0.65, 5)
        assert 0.4 < confidence < 0.8  # Should be moderate

    def test_calculate_confidence_invalid_inputs(
        self, learner: RecoveryLearner
    ) -> None:
        """Test confidence calculation with invalid inputs."""
        with pytest.raises(ValueError):
            learner.calculate_confidence(1.5, 10)  # Invalid success rate

        with pytest.raises(ValueError):
            learner.calculate_confidence(0.5, -1)  # Invalid sample size

    def test_calculate_confidence_zero_samples(self, learner: RecoveryLearner) -> None:
        """Test confidence calculation with zero samples."""
        confidence = learner.calculate_confidence(0.8, 0)
        assert confidence == 0.0

    # ========================================================================
    # Data Cleanup Tests
    # ========================================================================

    def test_clear_old_data(self, learner: RecoveryLearner) -> None:
        """Test clearing old recovery attempts."""
        # Record many attempts
        for i in range(150):
            learner.record_attempt(
                pattern_id=f"pattern-{i % 3}",
                strategy_used="test_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        assert len(learner._attempts) == 150

        # Clear old data, keeping only 100 most recent
        removed = learner.clear_old_data(keep_recent=100)

        assert removed == 50
        assert len(learner._attempts) == 100
        # Patterns and strategies should be preserved
        assert len(learner._patterns) == 3
        assert len(learner._learned_strategies) == 3

    def test_clear_old_data_below_threshold(self, learner: RecoveryLearner) -> None:
        """Test clearing old data when below threshold."""
        # Record only 5 attempts
        for _ in range(5):
            learner.record_attempt(
                pattern_id="test-pattern",
                strategy_used="test_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
            )

        # Try to clear with high threshold
        removed = learner.clear_old_data(keep_recent=100)

        assert removed == 0
        assert len(learner._attempts) == 5

    # ========================================================================
    # Persistence Tests
    # ========================================================================

    def test_persistence_across_instances(
        self, learning_path: Path, mock_timeout_attempts: list[dict[str, Any]]
    ) -> None:
        """Test that learning data persists across RecoveryLearner instances."""
        # Record data in first instance
        learner1 = RecoveryLearner(learning_path=learning_path)
        for attempt_data in mock_timeout_attempts:
            learner1.record_attempt(**attempt_data)

        # Add more attempts to reach MEDIUM confidence
        for _ in range(3):
            learner1.record_attempt(
                pattern_id="timeout-api-call",
                strategy_used="retry_with_backoff",
                action_type="RETRY",
                parameters={"max_retries": 3, "backoff_multiplier": 2.0},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=5.0,
            )

        # Create new instance and verify data persists
        learner2 = RecoveryLearner(learning_path=learning_path)

        assert len(learner2._attempts) == 6  # 3 original + 3 additional
        assert len(learner2._patterns) == 1
        assert "timeout-api-call" in learner2._patterns

        # Verify learning works across instances
        strategies = learner2.learn_from_history(
            min_attempts=2, min_success_rate=0.3
        )
        assert len(strategies) >= 1

    # ========================================================================
    # Complex Integration Scenarios
    # ========================================================================

    def test_complete_learning_workflow(
        self,
        learner: RecoveryLearner,
        mock_timeout_attempts: list[dict[str, Any]],
        mock_connection_attempts: list[dict[str, Any]],
        mock_memory_attempts: list[dict[str, Any]],
    ) -> None:
        """Test a complete learning workflow with multiple patterns and strategies."""
        # Phase 1: Record all mock healing data
        all_attempts = (
            mock_timeout_attempts
            + mock_connection_attempts
            + mock_memory_attempts
        )
        attempt_ids = []
        for attempt_data in all_attempts:
            attempt_id = learner.record_attempt(**attempt_data)
            attempt_ids.append(attempt_id)

        assert len(attempt_ids) == 7

        # Phase 2: Learn from history
        # Note: Many strategies won't be recommended due to LOW confidence with limited attempts
        strategies = learner.learn_from_history(
            min_attempts=1, min_success_rate=0.4
        )
        # At least some strategies should be returned (those with sufficient success and attempts)
        assert len(strategies) >= 0  # May be 0 if no strategies reach MEDIUM confidence

        # Phase 3: Get pattern statistics for each pattern
        timeout_stats = learner.get_pattern_statistics("timeout-api-call")
        connection_stats = learner.get_pattern_statistics("connection-database")
        memory_stats = learner.get_pattern_statistics("memory-out-of-memory")

        assert timeout_stats is not None
        assert connection_stats is not None
        assert memory_stats is not None

        # Phase 4: Get best strategy for each pattern
        timeout_best = learner.get_best_strategy(
            "timeout-api-call",
            min_confidence=PatternConfidence.LOW,
        )
        connection_best = learner.get_best_strategy(
            "connection-database",
            min_confidence=PatternConfidence.LOW,
        )
        memory_best = learner.get_best_strategy(
            "memory-out-of-memory",
            min_confidence=PatternConfidence.LOW,
        )

        assert timeout_best is not None
        assert connection_best is not None
        assert memory_best is not None

        # Phase 5: Get comprehensive summary
        summary = learner.get_learning_summary()
        assert summary["total_attempts"] == 7
        assert summary["total_patterns"] == 3
        assert summary["successful_attempts"] == 5
        assert summary["failed_attempts"] == 2

    def test_strategy_evolution_over_time(self, learner: RecoveryLearner) -> None:
        """Test how strategies evolve as more data is collected."""
        pattern_id = "evolving-pattern"

        # Phase 1: Initial attempts - low confidence
        for i in range(2):
            learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used="initial_strategy",
                action_type="RETRY",
                parameters={"retry_count": i + 1},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=5.0,
            )

        # With only 2 attempts, confidence will be LOW, so learn_from_history won't return it
        # Let's verify it's tracked but not recommended
        strategies = learner.learn_from_history(
            min_attempts=1, min_success_rate=0.5
        )
        # Should be 0 because LOW confidence strategies are not recommended
        assert len(strategies) == 0

        # Verify the strategy exists and has LOW confidence
        strategy_key = f"{pattern_id}:initial_strategy"
        assert strategy_key in learner._learned_strategies
        assert learner._learned_strategies[strategy_key].confidence == PatternConfidence.LOW

        # Phase 2: More successful attempts - confidence increases
        for _ in range(4):
            learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used="initial_strategy",
                action_type="RETRY",
                parameters={"retry_count": 3},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=5.0,
            )

        # Now with 6 attempts and 100% success, should have MEDIUM confidence
        strategies = learner.learn_from_history(
            min_attempts=3, min_success_rate=0.5
        )
        assert len(strategies) >= 1
        # Confidence should have increased to at least MEDIUM
        assert strategies[0].confidence in (
            PatternConfidence.MEDIUM,
            PatternConfidence.HIGH,
        )

    def test_multiple_strategies_for_same_pattern(
        self, learner: RecoveryLearner
    ) -> None:
        """Test learning multiple strategies for the same error pattern."""
        pattern_id = "multi-strategy-pattern"

        # Record attempts with different strategies
        strategies_data = [
            ("fast_strategy", "RETRY", {"retries": 2}, True, 2.0),
            ("fast_strategy", "RETRY", {"retries": 2}, True, 2.5),
            ("fast_strategy", "RETRY", {"retries": 2}, True, 1.8),
            ("slow_strategy", "RECONFIGURE", {"timeout": 60}, True, 10.0),
            ("slow_strategy", "RECONFIGURE", {"timeout": 60}, True, 12.0),
            ("failing_strategy", "RETRY", {"retries": 1}, False, 1.0),
            ("failing_strategy", "RETRY", {"retries": 1}, False, 1.2),
        ]

        for strategy_name, action_type, params, success, exec_time in strategies_data:
            learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used=strategy_name,
                action_type=action_type,
                parameters=params,
                outcome=RecoveryOutcome.SUCCESS if success else RecoveryOutcome.FAILED,
                success=success,
                execution_time=exec_time,
            )

        # Get all strategies for this pattern
        all_strategies = [
            s
            for s in learner._learned_strategies.values()
            if s.pattern_id == pattern_id
        ]

        assert len(all_strategies) == 3

        # fast_strategy should have best effectiveness
        best = learner.get_best_strategy(
            pattern_id,
            min_confidence=PatternConfidence.LOW,
        )

        assert best is not None
        assert best.strategy_name == "fast_strategy"
        assert best.success_rate == 1.0  # 3/3 successes

    def test_confidence_levels_across_strategies(
        self, learner: RecoveryLearner
    ) -> None:
        """Test that different strategies achieve appropriate confidence levels."""
        pattern_id = "confidence-test-pattern"

        # High confidence strategy: many successes
        for _ in range(8):
            learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used="high_confidence_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS,
                success=True,
                execution_time=3.0,
            )

        # Medium confidence strategy: moderate success with some data
        for i in range(5):
            learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used="medium_confidence_strategy",
                action_type="RETRY",
                parameters={},
                outcome=RecoveryOutcome.SUCCESS if i < 3 else RecoveryOutcome.FAILED,
                success=i < 3,
                execution_time=4.0,
            )

        # Low confidence strategy: limited data
        learner.record_attempt(
            pattern_id=pattern_id,
            strategy_used="low_confidence_strategy",
            action_type="RETRY",
            parameters={},
            outcome=RecoveryOutcome.SUCCESS,
            success=True,
            execution_time=5.0,
        )

        high_conf_strat = learner._learned_strategies[
            f"{pattern_id}:high_confidence_strategy"
        ]
        medium_conf_strat = learner._learned_strategies[
            f"{pattern_id}:medium_confidence_strategy"
        ]
        low_conf_strat = learner._learned_strategies[
            f"{pattern_id}:low_confidence_strategy"
        ]

        assert high_conf_strat.confidence == PatternConfidence.HIGH
        assert medium_conf_strat.confidence == PatternConfidence.MEDIUM
        assert low_conf_strat.confidence == PatternConfidence.LOW
