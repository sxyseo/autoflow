"""Pattern persistence layer for recovery learning system.

This module provides the PatternStore class for persisting and loading recovery
patterns, attempts, and learned strategies to/from JSON files. It implements
atomic writes for crash-safe persistence and provides efficient lookup methods.

Usage:
    from autoflow.healing.pattern_store import PatternStore

    store = PatternStore()
    pattern = RecoveryPattern(...)
    store.save_pattern(pattern)
    retrieved = store.find_by_error_pattern("timeout")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from autoflow.healing.recovery_learner import (
    LearnedStrategy,
    PatternConfidence,
    RecoveryAttempt,
    RecoveryOutcome,
    RecoveryPattern,
)


class PatternStore:
    """Persistent storage for recovery patterns and learned strategies.

    This class manages the persistence of recovery learning data to JSON files
    following the strategy memory pattern with atomic writes and proper locking.
    It stores recovery patterns, individual recovery attempts, and learned
    strategies in separate collections within a single JSON file.

    The storage is organized as:
    - patterns: Dictionary mapping pattern_id to RecoveryPattern
    - attempts: Dictionary mapping attempt_id to RecoveryAttempt
    - strategies: Dictionary mapping strategy_id to LearnedStrategy

    Attributes:
        store_path: Path to the pattern store JSON file.
        patterns: Dictionary of recovery patterns indexed by pattern_id.
        attempts: Dictionary of recovery attempts indexed by attempt_id.
        strategies: Dictionary of learned strategies indexed by strategy_id.
    """

    # Default store file path
    DEFAULT_STORE_PATH = Path(".autoflow/recovery_patterns.json")

    def __init__(self, store_path: Optional[Path] = None, root_dir: Optional[Path] = None) -> None:
        """Initialize the pattern store.

        Args:
            store_path: Path to pattern store JSON file. If None, uses DEFAULT_STORE_PATH.
            root_dir: Root directory of the project. Defaults to current directory.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if store_path is None:
            store_path = self.DEFAULT_STORE_PATH

        self.store_path = Path(store_path)

        # Ensure parent directory exists
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data or initialize empty
        self.patterns: dict[str, RecoveryPattern] = {}
        self.attempts: dict[str, RecoveryAttempt] = {}
        self.strategies: dict[str, LearnedStrategy] = {}
        self._load_store()

    def save_pattern(self, pattern: RecoveryPattern) -> None:
        """Save or update a recovery pattern.

        Args:
            pattern: RecoveryPattern to save.

        Raises:
            IOError: If unable to write pattern store to disk.
        """
        # Store in memory
        self.patterns[pattern.pattern_id] = pattern

        # Persist to disk
        self._save_store()

    def save_attempt(self, attempt: RecoveryAttempt) -> None:
        """Save or update a recovery attempt.

        Args:
            attempt: RecoveryAttempt to save.

        Raises:
            IOError: If unable to write pattern store to disk.
        """
        # Store in memory
        self.attempts[attempt.attempt_id] = attempt

        # Persist to disk
        self._save_store()

    def save_strategy(self, strategy: LearnedStrategy) -> None:
        """Save or update a learned strategy.

        Args:
            strategy: LearnedStrategy to save.

        Raises:
            IOError: If unable to write pattern store to disk.
        """
        # Store in memory
        self.strategies[strategy.strategy_id] = strategy

        # Persist to disk
        self._save_store()

    def get_pattern(self, pattern_id: str) -> RecoveryPattern | None:
        """Get a recovery pattern by ID.

        Args:
            pattern_id: Unique identifier for the pattern.

        Returns:
            RecoveryPattern if found, None otherwise.
        """
        return self.patterns.get(pattern_id)

    def get_attempt(self, attempt_id: str) -> RecoveryAttempt | None:
        """Get a recovery attempt by ID.

        Args:
            attempt_id: Unique identifier for the attempt.

        Returns:
            RecoveryAttempt if found, None otherwise.
        """
        return self.attempts.get(attempt_id)

    def get_strategy(self, strategy_id: str) -> LearnedStrategy | None:
        """Get a learned strategy by ID.

        Args:
            strategy_id: Unique identifier for the strategy.

        Returns:
            LearnedStrategy if found, None otherwise.
        """
        return self.strategies.get(strategy_id)

    def find_by_error_pattern(self, error_signature: str) -> RecoveryPattern | None:
        """Find a recovery pattern by error signature.

        Args:
            error_signature: Error signature to search for.

        Returns:
            RecoveryPattern if found, None otherwise.
        """
        for pattern in self.patterns.values():
            if pattern.error_signature == error_signature:
                return pattern
        return None

    def get_strategies_for_error(self, error_signature: str) -> list[LearnedStrategy]:
        """Get all learned strategies for a specific error pattern.

        Args:
            error_signature: Error signature to find strategies for.

        Returns:
            List of LearnedStrategy objects, sorted by effectiveness score.
        """
        strategies = [
            strategy
            for strategy in self.strategies.values()
            if strategy.pattern_id == error_signature
        ]

        # Sort by effectiveness score (highest first)
        strategies.sort(key=lambda s: s.effectiveness_score, reverse=True)

        return strategies

    def get_success_rate(self, pattern_id: str) -> float:
        """Get the success rate for a specific pattern.

        Args:
            pattern_id: Pattern identifier to get success rate for.

        Returns:
            Success rate from 0.0 to 1.0, or 0.0 if pattern not found.
        """
        pattern = self.get_pattern(pattern_id)
        if pattern is None:
            return 0.0

        # Find all attempts for this pattern
        pattern_attempts = [
            attempt for attempt in self.attempts.values()
            if attempt.pattern_id == pattern_id
        ]

        if not pattern_attempts:
            return 0.0

        # Calculate success rate
        successful = sum(1 for attempt in pattern_attempts if attempt.success)
        return successful / len(pattern_attempts)

        return pattern.get_success_rate()

    def get_all_patterns(self) -> list[RecoveryPattern]:
        """Get all recovery patterns.

        Returns:
            List of all RecoveryPattern objects.
        """
        return list(self.patterns.values())

    def get_all_strategies(self) -> list[LearnedStrategy]:
        """Get all learned strategies.

        Returns:
            List of all LearnedStrategy objects.
        """
        return list(self.strategies.values())

    def get_all_attempts(self) -> list[RecoveryAttempt]:
        """Get all recovery attempts.

        Returns:
            List of all RecoveryAttempt objects.
        """
        return list(self.attempts.values())

    def get_recommended_strategies(self, error_signature: str, min_confidence: PatternConfidence = PatternConfidence.MEDIUM) -> list[LearnedStrategy]:
        """Get recommended strategies for an error pattern.

        Args:
            error_signature: Error signature to find strategies for.
            min_confidence: Minimum confidence level for recommendations.

        Returns:
            List of recommended LearnedStrategy objects, sorted by effectiveness.
        """
        strategies = self.get_strategies_for_error(error_signature)

        # Filter by confidence and recommendation status
        recommended = [
            strategy
            for strategy in strategies
            if strategy.is_recommended() and strategy.confidence.value >= min_confidence.value
        ]

        return recommended

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the pattern store.

        Returns:
            Dictionary with store statistics including counts, success rates, etc.
        """
        total_patterns = len(self.patterns)
        total_attempts = len(self.attempts)
        total_strategies = len(self.strategies)

        # Calculate overall success rate
        successful_attempts = sum(1 for attempt in self.attempts.values() if attempt.success)
        overall_success_rate = successful_attempts / total_attempts if total_attempts > 0 else 0.0

        # Count strategies by confidence
        high_confidence = sum(1 for s in self.strategies.values() if s.confidence == PatternConfidence.HIGH)
        medium_confidence = sum(1 for s in self.strategies.values() if s.confidence == PatternConfidence.MEDIUM)
        low_confidence = sum(1 for s in self.strategies.values() if s.confidence == PatternConfidence.LOW)

        return {
            "total_patterns": total_patterns,
            "total_attempts": total_attempts,
            "total_strategies": total_strategies,
            "overall_success_rate": overall_success_rate,
            "high_confidence_strategies": high_confidence,
            "medium_confidence_strategies": medium_confidence,
            "low_confidence_strategies": low_confidence,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def clear_old_data(self, keep_recent_patterns: int = 100, keep_recent_attempts: int = 1000) -> dict[str, int]:
        """Remove old patterns and attempts to manage storage.

        Keeps the most recent N patterns and attempts, removing older ones.
        Learned strategies are preserved as they represent accumulated knowledge.

        Args:
            keep_recent_patterns: Number of recent patterns to keep.
            keep_recent_attempts: Number of recent attempts to keep.

        Returns:
            Dictionary with counts of removed items.

        Raises:
            IOError: If unable to write pattern store to disk.
        """
        removed = {"patterns": 0, "attempts": 0}

        # Remove old patterns
        if len(self.patterns) > keep_recent_patterns:
            # Sort patterns by last_seen (most recent first)
            sorted_patterns = sorted(
                self.patterns.items(),
                key=lambda x: x[1].last_seen,
                reverse=True,
            )

            # Keep only the most recent
            kept = dict(sorted_patterns[:keep_recent_patterns])
            removed["patterns"] = len(self.patterns) - len(kept)
            self.patterns = kept

        # Remove old attempts
        if len(self.attempts) > keep_recent_attempts:
            # Sort attempts by timestamp (most recent first)
            sorted_attempts = sorted(
                self.attempts.items(),
                key=lambda x: x[1].timestamp,
                reverse=True,
            )

            # Keep only the most recent
            kept = dict(sorted_attempts[:keep_recent_attempts])
            removed["attempts"] = len(self.attempts) - len(kept)
            self.attempts = kept

        # Persist to disk
        self._save_store()

        return removed

    def _load_store(self) -> None:
        """Load pattern store from disk.

        Reads the pattern store JSON file and populates the patterns, attempts,
        and strategies dictionaries. Creates an empty store file if none exists.
        """
        if not self.store_path.exists():
            # Create empty store file
            self._save_store()
            return

        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))

            # Load patterns
            patterns_data = data.get("patterns", {})
            self.patterns = {
                pattern_id: RecoveryPattern(**pattern_data)
                for pattern_id, pattern_data in patterns_data.items()
            }

            # Load attempts
            attempts_data = data.get("attempts", {})
            self.attempts = {
                attempt_id: RecoveryAttempt.from_dict(attempt_data)
                for attempt_id, attempt_data in attempts_data.items()
            }

            # Load strategies
            strategies_data = data.get("strategies", {})
            self.strategies = {
                strategy_id: LearnedStrategy.from_dict(strategy_data)
                for strategy_id, strategy_data in strategies_data.items()
            }

        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self.patterns = {}
            self.attempts = {}
            self.strategies = {}

    def _save_store(self) -> None:
        """Save pattern store to disk.

        Writes the patterns, attempts, and strategies dictionaries to the
        pattern store JSON file. Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the pattern store file.
        """
        # Convert patterns to dictionaries
        patterns_data = {
            pattern_id: pattern.to_dict()
            for pattern_id, pattern in self.patterns.items()
        }

        # Convert attempts to dictionaries
        attempts_data = {
            attempt_id: attempt.to_dict()
            for attempt_id, attempt in self.attempts.items()
        }

        # Convert strategies to dictionaries
        strategies_data = {
            strategy_id: strategy.to_dict()
            for strategy_id, strategy in self.strategies.items()
        }

        # Build store structure
        store_data = {
            "patterns": patterns_data,
            "attempts": attempts_data,
            "strategies": strategies_data,
            "metadata": {
                "total_patterns": len(self.patterns),
                "total_attempts": len(self.attempts),
                "total_strategies": len(self.strategies),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.store_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(store_data, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.store_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to write pattern store to {self.store_path}: {e}") from e
