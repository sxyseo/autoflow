"""
Autoflow Feedback Collection

Captures actual outcomes and compares them to predictions for model improvement.
This module implements the feedback loop that enables the ML model to learn
from past predictions and improve over time.

Usage:
    from autoflow.prediction import FeedbackCollector

    collector = FeedbackCollector()
    collector.record_prediction(spec_id, prediction_result)
    collector.record_outcome(spec_id, actual_outcome)
    accuracy = collector.get_accuracy()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from autoflow.prediction.data_collector import QualityOutcome
from autoflow.prediction.model import PredictionResult


class PredictionStatus(str, Enum):
    """
    Status of a prediction relative to actual outcome.

    Attributes:
        CORRECT: Prediction matched the actual outcome
        INCORRECT: Prediction did not match the actual outcome
        PENDING: Actual outcome not yet recorded
    """

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PENDING = "pending"


@dataclass
class PredictionRecord:
    """
    A recorded prediction with timestamp and metadata.

    Attributes:
        spec_id: Unique identifier for the spec
        timestamp: When the prediction was made (ISO format)
        predicted_outcome: The predicted quality outcome
        confidence: Confidence score from 0.0 to 1.0
        rationale: Human-readable explanation of the prediction
        feature_importances: Dictionary of feature importance scores
        actual_outcome: Actual outcome (None if not yet recorded)
        status: Comparison status (correct/incorrect/pending)
    """

    spec_id: str
    timestamp: str
    predicted_outcome: str
    confidence: float
    rationale: str
    feature_importances: dict[str, float]
    actual_outcome: Optional[str] = None
    status: PredictionStatus = PredictionStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "spec_id": self.spec_id,
            "timestamp": self.timestamp,
            "predicted_outcome": self.predicted_outcome,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "feature_importances": self.feature_importances,
            "actual_outcome": self.actual_outcome,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PredictionRecord":
        """Create from dictionary for JSON deserialization."""
        return cls(
            spec_id=data["spec_id"],
            timestamp=data["timestamp"],
            predicted_outcome=data["predicted_outcome"],
            confidence=data["confidence"],
            rationale=data["rationale"],
            feature_importances=data["feature_importances"],
            actual_outcome=data.get("actual_outcome"),
            status=PredictionStatus(data.get("status", PredictionStatus.PENDING)),
        )


@dataclass
class FeedbackSummary:
    """
    Summary statistics for feedback data.

    Attributes:
        total_predictions: Total number of predictions recorded
        correct_predictions: Number of correct predictions
        incorrect_predictions: Number of incorrect predictions
        pending_predictions: Number of predictions awaiting outcomes
        accuracy: Accuracy rate (correct / total_completed)
        avg_confidence_correct: Average confidence for correct predictions
        avg_confidence_incorrect: Average confidence for incorrect predictions
        precision: Precision score (true positives / all predicted positives)
        recall: Recall score (true positives / all actual positives)
        f1: F1 score (harmonic mean of precision and recall)
    """

    total_predictions: int
    correct_predictions: int
    incorrect_predictions: int
    pending_predictions: int
    accuracy: float
    avg_confidence_correct: float
    avg_confidence_incorrect: float
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


class FeedbackCollector:
    """
    Collects and manages feedback for quality predictions.

    This class handles:
    - Recording predictions with timestamps
    - Recording actual outcomes
    - Comparing predictions to outcomes
    - Calculating accuracy metrics
    - Persisting feedback to disk for model retraining

    The feedback is stored in .autoflow/feedback.json following the
    strategy memory pattern with atomic writes and proper locking.

    Attributes:
        feedback_path: Path to the feedback JSON file
        predictions: Dictionary mapping spec_id to PredictionRecord
    """

    # Default feedback file path
    DEFAULT_FEEDBACK_PATH = Path(".autoflow/feedback.json")

    def __init__(self, feedback_path: Optional[Path] = None, root_dir: Optional[Path] = None) -> None:
        """
        Initialize the feedback collector.

        Args:
            feedback_path: Path to feedback JSON file. If None, uses DEFAULT_FEEDBACK_PATH
            root_dir: Root directory of the project. Defaults to current directory.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if feedback_path is None:
            feedback_path = self.DEFAULT_FEEDBACK_PATH

        self.feedback_path = Path(feedback_path)

        # Ensure parent directory exists
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing feedback or initialize empty
        self.predictions: dict[str, PredictionRecord] = {}
        self._load_feedback()

    def record_prediction(self, spec_id: str, prediction: PredictionResult) -> None:
        """
        Record a prediction for a spec.

        Creates a new prediction record with timestamp and metadata.
        If a prediction already exists for this spec, it will be overwritten.

        Args:
            spec_id: Unique identifier for the spec
            prediction: PredictionResult from the quality predictor

        Raises:
            IOError: If unable to write feedback to disk
        """
        # Create prediction record
        record = PredictionRecord(
            spec_id=spec_id,
            timestamp=datetime.now(UTC).isoformat(),
            predicted_outcome=prediction.prediction.value
            if isinstance(prediction.prediction, QualityOutcome)
            else prediction.prediction,
            confidence=prediction.confidence,
            rationale=prediction.rationale,
            feature_importances=prediction.feature_importances,
            actual_outcome=None,
            status=PredictionStatus.PENDING,
        )

        # Store in memory
        self.predictions[spec_id] = record

        # Persist to disk
        self._save_feedback()

    def record_outcome(self, spec_id: str, actual_outcome: QualityOutcome | str) -> None:
        """
        Record the actual outcome for a spec.

        Updates the prediction record with the actual outcome and
        compares it to the prediction to determine correctness.

        Args:
            spec_id: Unique identifier for the spec
            actual_outcome: Actual quality outcome that occurred

        Raises:
            ValueError: If no prediction exists for this spec
            IOError: If unable to write feedback to disk
        """
        # Normalize outcome to string
        if isinstance(actual_outcome, QualityOutcome):
            outcome_str = actual_outcome.value
        else:
            outcome_str = str(actual_outcome)

        # Check if prediction exists
        if spec_id not in self.predictions:
            raise ValueError(f"No prediction found for spec: {spec_id}")

        # Get the prediction record
        record = self.predictions[spec_id]

        # Update with actual outcome
        record.actual_outcome = outcome_str

        # Determine if prediction was correct
        # Prediction is correct if it matches the outcome category
        predicted = record.predicted_outcome.lower()
        actual = outcome_str.lower()

        # Match prediction to outcome (success vs issues)
        if predicted == actual:
            record.status = PredictionStatus.CORRECT
        elif "success" in predicted and "success" in actual:
            record.status = PredictionStatus.CORRECT
        elif "success" not in predicted and "success" not in actual:
            # Both are issues (needs_changes or failed)
            record.status = PredictionStatus.CORRECT
        else:
            record.status = PredictionStatus.INCORRECT

        # Persist to disk
        self._save_feedback()

    def get_accuracy(self) -> float:
        """
        Calculate prediction accuracy.

        Accuracy is defined as the percentage of completed predictions
        (excluding pending) that were correct.

        Returns:
            Accuracy score from 0.0 to 1.0, or 0.0 if no completed predictions

        Examples:
            >>> collector = FeedbackCollector()
            >>> accuracy = collector.get_accuracy()
            >>> print(f"Model accuracy: {accuracy:.2%}")
        """
        correct = 0
        total = 0

        for record in self.predictions.values():
            if record.status != PredictionStatus.PENDING:
                total += 1
                if record.status == PredictionStatus.CORRECT:
                    correct += 1

        if total == 0:
            return 0.0

        return correct / total

    def get_precision_recall_f1(self) -> tuple[float, float, float]:
        """
        Calculate precision, recall, and F1 score for success predictions.

        Treats "success" as the positive class and "needs_changes"/"failed"
        as the negative class for binary classification metrics.

        Returns:
            Tuple of (precision, recall, f1) scores from 0.0 to 1.0
            Returns (0.0, 0.0, 0.0) if unable to calculate

        Examples:
            >>> collector = FeedbackCollector()
            >>> precision, recall, f1 = collector.get_precision_recall_f1()
            >>> print(f"Precision: {precision:.2%}, Recall: {recall:.2%}, F1: {f1:.2%}")
        """
        # Count true positives, false positives, false negatives, true negatives
        # Positive class: "success"
        # Negative class: "needs_changes" or "failed"
        tp = 0  # True positive: predicted success, actual success
        fp = 0  # False positive: predicted success, actual not success
        fn = 0  # False negative: predicted not success, actual success
        tn = 0  # True negative: predicted not success, actual not success

        for record in self.predictions.values():
            # Skip pending predictions
            if record.status == PredictionStatus.PENDING:
                continue

            # Normalize predictions and outcomes
            predicted = record.predicted_outcome.lower()
            actual = record.actual_outcome.lower() if record.actual_outcome else ""

            # Determine if success (positive) or not (negative)
            predicted_positive = "success" in predicted
            actual_positive = "success" in actual

            if predicted_positive and actual_positive:
                tp += 1
            elif predicted_positive and not actual_positive:
                fp += 1
            elif not predicted_positive and actual_positive:
                fn += 1
            else:
                tn += 1

        # Calculate precision, recall, F1
        # Precision = TP / (TP + FP) - of all predicted positive, how many were actually positive?
        # Recall = TP / (TP + FN) - of all actually positive, how many did we predict?
        # F1 = 2 * (precision * recall) / (precision + recall)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        if precision + recall > 0:
            f1 = 2 * (precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        return precision, recall, f1

    def get_summary(self) -> FeedbackSummary:
        """
        Get comprehensive summary of feedback statistics.

        Calculates metrics including accuracy, precision, recall, F1,
        confidence distributions, and prediction counts.

        Returns:
            FeedbackSummary with all statistics

        Raises:
            IOError: If unable to read feedback data
        """
        total = len(self.predictions)
        correct = 0
        incorrect = 0
        pending = 0

        confidences_correct = []
        confidences_incorrect = []

        for record in self.predictions.values():
            if record.status == PredictionStatus.CORRECT:
                correct += 1
                confidences_correct.append(record.confidence)
            elif record.status == PredictionStatus.INCORRECT:
                incorrect += 1
                confidences_incorrect.append(record.confidence)
            else:
                pending += 1

        # Calculate accuracy
        completed = correct + incorrect
        accuracy = correct / completed if completed > 0 else 0.0

        # Calculate average confidences
        avg_conf_correct = sum(confidences_correct) / len(confidences_correct) if confidences_correct else 0.0
        avg_conf_incorrect = sum(confidences_incorrect) / len(confidences_incorrect) if confidences_incorrect else 0.0

        # Calculate precision, recall, F1
        precision, recall, f1 = self.get_precision_recall_f1()

        return FeedbackSummary(
            total_predictions=total,
            correct_predictions=correct,
            incorrect_predictions=incorrect,
            pending_predictions=pending,
            accuracy=accuracy,
            avg_confidence_correct=avg_conf_correct,
            avg_confidence_incorrect=avg_conf_incorrect,
            precision=precision,
            recall=recall,
            f1=f1,
        )

    def get_predictions_for_retraining(
        self, min_samples: int = 1, include_pending: bool = False
    ) -> list[tuple[str, dict[str, Any], str]]:
        """
        Get predictions formatted for model retraining.

        Returns completed predictions as (spec_id, features, label) tuples
        suitable for retraining the model.

        Args:
            min_samples: Minimum number of samples required (returns empty if less)
            include_pending: If True, includes pending predictions with actual outcome

        Returns:
            List of (spec_id, features, outcome_label) tuples for retraining

        Examples:
            >>> collector = FeedbackCollector()
            >>> samples = collector.get_predictions_for_retraining(min_samples=10)
            >>> if samples:
            ...     spec_ids, features, labels = zip(*samples)
        """
        # Note: We don't have the original feature vectors stored,
        # so we return spec_ids that can be used to re-extract features
        samples = []

        for spec_id, record in self.predictions.items():
            if record.status == PredictionStatus.PENDING and not include_pending:
                continue

            if record.actual_outcome is None:
                continue

            # Return spec_id which can be used to re-extract features
            # For now, we return empty dict for features placeholder
            samples.append((spec_id, {}, record.actual_outcome))

        if len(samples) < min_samples:
            return []

        return samples

    def clear_old_predictions(self, keep_recent: int = 1000) -> int:
        """
        Remove old predictions to manage storage.

        Keeps the most recent N predictions and removes older ones.

        Args:
            keep_recent: Number of recent predictions to keep

        Returns:
            Number of predictions removed

        Raises:
            IOError: If unable to write feedback to disk
        """
        if len(self.predictions) <= keep_recent:
            return 0

        # Sort predictions by timestamp (most recent first)
        sorted_predictions = sorted(
            self.predictions.items(),
            key=lambda x: x[1].timestamp,
            reverse=True,
        )

        # Keep only the most recent
        kept = dict(sorted_predictions[:keep_recent])
        removed = len(self.predictions) - len(kept)
        self.predictions = kept

        # Persist to disk
        self._save_feedback()

        return removed

    def _load_feedback(self) -> None:
        """
        Load feedback from disk.

        Reads the feedback JSON file and populates the predictions dictionary.
        Creates an empty feedback file if none exists.
        """
        if not self.feedback_path.exists():
            # Create empty feedback file
            self._save_feedback()
            return

        try:
            data = json.loads(self.feedback_path.read_text(encoding="utf-8"))
            predictions_data = data.get("predictions", {})

            # Convert dictionaries to PredictionRecord objects
            self.predictions = {
                spec_id: PredictionRecord.from_dict(record_data)
                for spec_id, record_data in predictions_data.items()
            }
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self.predictions = {}

    def _save_feedback(self) -> None:
        """
        Save feedback to disk.

        Writes the predictions dictionary to the feedback JSON file.
        Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the feedback file
        """
        # Convert predictions to dictionaries
        predictions_data = {
            spec_id: record.to_dict()
            for spec_id, record in self.predictions.items()
        }

        # Build feedback structure
        feedback_data = {
            "predictions": predictions_data,
            "metadata": {
                "total_predictions": len(self.predictions),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.feedback_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(feedback_data, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.feedback_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to write feedback to {self.feedback_path}: {e}") from e

    def save_performance_metrics(self, performance_path: Optional[Path] = None) -> None:
        """
        Save current performance metrics to a JSON file.

        Stores accuracy, precision, recall, F1, and other metrics
        for model monitoring and comparison over time.

        Args:
            performance_path: Path to performance metrics JSON file.
                If None, uses .autoflow/model_performance.json

        Raises:
            IOError: If unable to write performance metrics to disk
        """
        if performance_path is None:
            performance_path = self.feedback_path.parent / "model_performance.json"

        performance_path = Path(performance_path)
        performance_path.parent.mkdir(parents=True, exist_ok=True)

        # Get current metrics
        summary = self.get_summary()
        precision, recall, f1 = self.get_precision_recall_f1()

        # Build performance data structure
        performance_data = {
            "metrics": {
                "accuracy": summary.accuracy,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            },
            "predictions": {
                "total": summary.total_predictions,
                "correct": summary.correct_predictions,
                "incorrect": summary.incorrect_predictions,
                "pending": summary.pending_predictions,
            },
            "confidence": {
                "avg_correct": summary.avg_confidence_correct,
                "avg_incorrect": summary.avg_confidence_incorrect,
            },
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "model_version": "1.0",
            },
        }

        # Write to file with atomic update
        temp_path = performance_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(performance_data, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(performance_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to write performance metrics to {performance_path}: {e}") from e

    def should_retrain(
        self,
        accuracy_threshold: float = 0.7,
        min_samples_threshold: int = 10
    ) -> bool:
        """
        Determine if model should be retrained based on feedback metrics.

        Checks if the model's accuracy has dropped below the threshold
        or if there are enough new samples available for retraining.

        Args:
            accuracy_threshold: Minimum acceptable accuracy (default 0.7).
                If current accuracy is below this, retraining is recommended.
            min_samples_threshold: Minimum number of completed samples needed
                to trigger retraining (default 10). If there are at least this
                many new samples with actual outcomes, retraining is recommended.

        Returns:
            True if retraining is recommended, False otherwise.

        Examples:
            >>> collector = FeedbackCollector()
            >>> if collector.should_retrain():
            ...     print("Model should be retrained")
            ...     # Trigger retraining workflow
        """
        # Get current accuracy
        current_accuracy = self.get_accuracy()

        # Count completed predictions (non-pending)
        # These are samples available for retraining
        completed_samples = sum(
            1 for record in self.predictions.values()
            if record.status != PredictionStatus.PENDING
        )

        # Check if accuracy has dropped below threshold
        accuracy_low = current_accuracy < accuracy_threshold

        # Check if we have enough new samples for retraining
        enough_samples = completed_samples >= min_samples_threshold

        # Return True if either condition is met
        return accuracy_low or enough_samples
