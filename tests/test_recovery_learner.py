"""Unit Tests for Recovery Learner Data Models

Tests the RecoveryPattern, RecoveryAttempt, and LearnedStrategy dataclasses
for error recovery learning and pattern extraction.

These tests ensure proper serialization, deserialization, and business logic
for the recovery learning system.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest

from autoflow.healing.recovery_learner import (
    LearnedStrategy,
    PatternConfidence,
    RecoveryAttempt,
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
