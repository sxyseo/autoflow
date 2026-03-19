"""
Autoflow Task Priority Prediction Model

ML model for predicting task completion outcomes and priority scores.
Uses sklearn's RandomForest classifier for outcome prediction and
regression for priority scoring.

Usage:
    from autoflow.prediction.task_priority_model import TaskPriorityModel

    model = TaskPriorityModel()
    model.train(feature_dicts, outcome_labels)
    prediction = model.predict(feature_dict)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

from autoflow.prediction.task_history_collector import TaskOutcome


@dataclass
class ScoredTask:
    """
    A task with its priority score and ranking information.

    Attributes:
        task_id: Unique identifier for the task
        priority_score: Predicted priority score (higher = more urgent)
        rank: Position in ranked list (1 = highest priority)
        outcome: Predicted task outcome
        confidence: Confidence score for the prediction
        rationale: Human-readable explanation
    """

    task_id: str
    priority_score: float
    rank: int
    outcome: TaskOutcome | str = ""
    confidence: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        # Handle both TaskOutcome enum and string values
        outcome_value = (
            self.outcome.value
            if isinstance(self.outcome, TaskOutcome)
            else self.outcome
        )
        return {
            "task_id": self.task_id,
            "priority_score": self.priority_score,
            "rank": self.rank,
            "outcome": outcome_value,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass
class PriorityPredictionResult:
    """
    Result of a task priority prediction.

    Attributes:
        outcome: Predicted task outcome (completed/needs_work/blocked/etc)
        confidence: Confidence score from 0.0 to 1.0
        priority_score: Predicted priority score (higher = more urgent)
        feature_importances: Dictionary mapping feature names to importance scores
        rationale: Human-readable explanation of the prediction
    """

    outcome: TaskOutcome
    confidence: float
    priority_score: float
    feature_importances: dict[str, float] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        # Handle both TaskOutcome enum and string values
        outcome_value = (
            self.outcome.value if isinstance(self.outcome, TaskOutcome) else self.outcome
        )
        return {
            "outcome": outcome_value,
            "confidence": self.confidence,
            "priority_score": self.priority_score,
            "feature_importances": self.feature_importances,
            "rationale": self.rationale,
        }


class TaskPriorityModel:
    """
    ML model for predicting task completion outcomes and priority scores.

    Uses sklearn's RandomForest to predict:
    1. Task outcome (classification): completed, needs_work, blocked, in_progress, pending
    2. Priority score (regression): numeric score for task prioritization

    The model is trained on historical task data with features like:
    - Task complexity (description length, files to create/modify)
    - Dependencies (number of dependencies, blocking tasks)
    - Service assignment (backend, frontend, etc.)
    - Historical performance (average completion time, success rate)

    Attributes:
        classifier: RandomForest for outcome prediction
        regressor: RandomForest for priority score prediction
        label_encoder: Encoder for converting outcome labels to numeric values
        feature_names: List of feature names used for training
        is_trained: Whether the model has been trained
    """

    # Default model directory for automatic model management
    DEFAULT_MODEL_DIR = Path(".autoflow/models")

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int | None = None,
        random_state: int = 42,
    ) -> None:
        """
        Initialize the task priority model.

        Args:
            n_estimators: Number of trees in the forest
            max_depth: Maximum depth of trees (None for unlimited)
            random_state: Random seed for reproducibility
        """
        self.classifier = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            class_weight="balanced",
        )
        self.regressor = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
        )
        self.label_encoder = LabelEncoder()
        self.feature_names: list[str] = []
        self.is_trained = False

    def train(
        self,
        features: list[dict[str, Any]],
        outcomes: list[str],
        priority_scores: list[float] | None = None,
    ) -> None:
        """
        Train the model on feature-outcome pairs.

        Args:
            features: List of feature dictionaries
            outcomes: List of outcome labels (completed/needs_work/blocked/etc)
            priority_scores: Optional list of priority scores for regression training

        Raises:
            ValueError: If features and outcomes have different lengths
        """
        if len(features) != len(outcomes):
            raise ValueError(
                f"Features and outcomes must have same length: "
                f"{len(features)} != {len(outcomes)}"
            )

        if not features:
            raise ValueError("Cannot train on empty dataset")

        # Extract feature names from first sample
        self.feature_names = list(features[0].keys())

        # Build feature matrix handling missing features
        feature_matrix = self._build_feature_matrix(features)

        # Train the outcome classifier
        self.classifier.fit(feature_matrix, outcomes)

        # Fit label encoder for later predictions
        self.label_encoder.fit(outcomes)

        # Train priority score regressor if scores provided
        if priority_scores and len(priority_scores) == len(features):
            # Filter out samples without priority scores
            valid_indices = [
                i for i, score in enumerate(priority_scores) if score is not None
            ]
            if valid_indices:
                valid_features = feature_matrix[valid_indices]
                valid_scores = [priority_scores[i] for i in valid_indices]
                self.regressor.fit(valid_features, valid_scores)

        self.is_trained = True

    def predict(self, features: dict[str, Any]) -> PriorityPredictionResult:
        """
        Make a prediction for a single feature set.

        Args:
            features: Feature dictionary

        Returns:
            PriorityPredictionResult with outcome, confidence, priority score, and rationale

        Raises:
            ValueError: If model is not trained
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        # Build feature vector for this sample
        feature_vector = self._build_feature_vector(features)

        # Reshape for sklearn (needs 2D array)
        feature_vector_reshaped = feature_vector.reshape(1, -1)

        # Get outcome prediction and probability
        outcome_prediction = self.classifier.predict(feature_vector_reshaped)[0]
        probabilities = self.classifier.predict_proba(feature_vector_reshaped)[0]

        # Get predicted class index for confidence calculation
        predicted_class_idx = list(self.label_encoder.classes_).index(outcome_prediction)
        confidence = float(probabilities[predicted_class_idx])

        # Predict priority score
        priority_score = float(self.regressor.predict(feature_vector_reshaped)[0])

        # Extract feature importances (use classifier importances)
        feature_importances = self._extract_feature_importances()

        # Generate rationale
        rationale = self._generate_rationale(features, feature_importances, outcome_prediction)

        return PriorityPredictionResult(
            outcome=outcome_prediction,
            confidence=confidence,
            priority_score=priority_score,
            feature_importances=feature_importances,
            rationale=rationale,
        )

    def predict_batch(
        self, features_list: list[dict[str, Any]]
    ) -> list[PriorityPredictionResult]:
        """
        Make predictions for multiple feature sets.

        Args:
            features_list: List of feature dictionaries

        Returns:
            List of PriorityPredictionResult objects

        Raises:
            ValueError: If model is not trained
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        results = []
        for features in features_list:
            result = self.predict(features)
            results.append(result)

        return results

    def score_tasks(
        self,
        tasks: list[dict[str, Any]],
        task_id_key: str = "task_id",
    ) -> list[ScoredTask]:
        """
        Score and rank multiple tasks by priority.

        This method predicts priority scores for each task and ranks them
        from highest to lowest priority. Higher scores indicate more urgent tasks.

        Args:
            tasks: List of task dictionaries containing features and task IDs.
                   Each dictionary should have a task_id field (or specified key)
                   and feature keys used during model training.
            task_id_key: Key name in task dictionary that contains the task ID.
                        Defaults to "task_id".

        Returns:
            List of ScoredTask objects sorted by priority (rank 1 = highest priority).

        Raises:
            ValueError: If model is not trained or if tasks are missing task IDs

        Example:
            >>> model = TaskPriorityModel()
            >>> model.train(features, outcomes, priority_scores)
            >>> tasks = [
            ...     {"task_id": "T1", "description_length": 100, "num_dependencies": 0},
            ...     {"task_id": "T2", "description_length": 500, "num_dependencies": 3},
            ... ]
            >>> scored_tasks = model.score_tasks(tasks)
            >>> for task in scored_tasks:
            ...     print(f"{task.task_id}: rank={task.rank}, score={task.priority_score:.2f}")
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before scoring tasks")

        if not tasks:
            return []

        # Validate tasks have task IDs
        scored_results = []
        for task in tasks:
            if task_id_key not in task:
                raise ValueError(
                    f"Task missing task ID key '{task_id_key}': {task}"
                )

            # Extract features (exclude task_id from features)
            features = {k: v for k, v in task.items() if k != task_id_key}

            # Get prediction for this task
            prediction = self.predict(features)

            scored_results.append(
                {
                    "task_id": task[task_id_key],
                    "priority_score": prediction.priority_score,
                    "outcome": prediction.outcome,
                    "confidence": prediction.confidence,
                    "rationale": prediction.rationale,
                }
            )

        # Sort by priority score (descending - higher score = higher priority)
        scored_results.sort(key=lambda x: x["priority_score"], reverse=True)

        # Assign ranks and create ScoredTask objects
        ranked_tasks = []
        for rank, result in enumerate(scored_results, start=1):
            ranked_tasks.append(
                ScoredTask(
                    task_id=result["task_id"],
                    priority_score=result["priority_score"],
                    rank=rank,
                    outcome=result["outcome"],
                    confidence=result["confidence"],
                    rationale=result["rationale"],
                )
            )

        return ranked_tasks

    def _build_feature_matrix(self, features: list[dict[str, Any]]) -> np.ndarray:
        """
        Build feature matrix from list of feature dictionaries.

        Handles missing features by filling with zeros.

        Args:
            features: List of feature dictionaries

        Returns:
            2D numpy array of features
        """
        # Get all unique feature names
        all_features = set()
        for feature_dict in features:
            all_features.update(feature_dict.keys())

        self.feature_names = sorted(all_features)

        # Build matrix row by row
        matrix = []
        for feature_dict in features:
            row = [feature_dict.get(name, 0.0) for name in self.feature_names]
            matrix.append(row)

        return np.array(matrix)

    def _build_feature_vector(self, features: dict[str, Any]) -> np.ndarray:
        """
        Build feature vector for a single feature dictionary.

        Handles missing features by filling with zeros.

        Args:
            features: Feature dictionary

        Returns:
            1D numpy array of features
        """
        vector = [features.get(name, 0.0) for name in self.feature_names]
        return np.array(vector)

    def _extract_feature_importances(self) -> dict[str, float]:
        """
        Extract feature importances from the trained classifier.

        Returns:
            Dictionary mapping feature names to importance scores
        """
        if not self.is_trained:
            return {}

        importances = self.classifier.feature_importances_

        return {
            name: float(importance)
            for name, importance in zip(self.feature_names, importances)
        }

    def _generate_rationale(
        self,
        features: dict[str, Any],
        importances: dict[str, float],
        outcome: TaskOutcome | str,
    ) -> str:
        """
        Generate human-readable rationale for the prediction.

        Args:
            features: Feature dictionary
            importances: Feature importance scores
            outcome: Predicted outcome

        Returns:
            Human-readable explanation
        """
        # Get top 3 most important features present in this sample
        feature_importance_pairs = [
            (name, importances.get(name, 0.0), features.get(name, 0.0))
            for name in self.feature_names
            if name in features
        ]

        # Sort by importance (descending)
        feature_importance_pairs.sort(key=lambda x: x[1], reverse=True)

        # Take top 3
        top_features = feature_importance_pairs[:3]

        # Build rationale
        parts = []

        for feature_name, importance, feature_value in top_features:
            if importance < 0.01:
                continue  # Skip very low importance features

            # Generate human-readable description
            description = self._describe_feature(feature_name, feature_value)
            if description:
                parts.append(description)

        if parts:
            return " | ".join(parts)

        return f"Prediction based on {len(features)} features"

    def _describe_feature(self, feature_name: str, value: Any) -> str:
        """
        Generate human-readable description for a feature value.

        Args:
            feature_name: Name of the feature
            value: Value of the feature

        Returns:
            Human-readable description
        """
        # Handle task complexity features
        if "description_length" in feature_name and isinstance(value, (int, float)):
            if value > 500:
                return "long description"
            elif value > 200:
                return "medium description"
            else:
                return "short description"

        elif "files_to_create" in feature_name and isinstance(value, (int, float)):
            if value > 5:
                return f"many files to create ({int(value)})"
            elif value > 0:
                return f"{int(value)} files to create"

        elif "files_to_modify" in feature_name and isinstance(value, (int, float)):
            if value > 5:
                return f"many files to modify ({int(value)})"
            elif value > 0:
                return f"{int(value)} files to modify"

        elif "has_verification" in feature_name:
            return "has verification" if value else "no verification"

        # Handle dependency features
        elif "num_dependencies" in feature_name and isinstance(value, (int, float)):
            if value > 3:
                return f"many dependencies ({int(value)})"
            elif value > 0:
                return f"{int(value)} dependencies"

        elif "num_dependents" in feature_name and isinstance(value, (int, float)):
            if value > 3:
                return f"blocks many tasks ({int(value)})"
            elif value > 0:
                return f"blocks {int(value)} tasks"

        elif "is_blocking" in feature_name:
            return "blocking task" if value else "non-blocking"

        elif "dependency_depth" in feature_name and isinstance(value, (int, float)):
            if value > 3:
                return f"deep dependency chain ({int(value)})"
            elif value > 0:
                return f"dependency depth {int(value)}"

        # Handle service features
        elif "task_service_" in feature_name and value:
            service = feature_name.replace("task_service_", "")
            return f"{service} service"

        elif "task_phase_type_" in feature_name and value:
            phase_type = feature_name.replace("task_phase_type_", "")
            return f"{phase_type} phase"

        # Handle historical features
        elif "avg_completion_time" in feature_name and isinstance(value, (int, float)):
            if value > 3600:
                return f"long avg completion ({value/3600:.1f}h)"
            elif value > 60:
                return f"moderate completion time ({value/60:.1f}m)"
            else:
                return f"fast completion ({value:.0f}s)"

        elif "success_rate" in feature_name and isinstance(value, (int, float)):
            if value < 0.5:
                return f"low success rate ({value:.0%})"
            elif value > 0.8:
                return f"high success rate ({value:.0%})"
            else:
                return f"moderate success rate ({value:.0%})"

        # Default: just return the feature name and value
        return f"{feature_name}: {value}"

    def save(self, path: Path | None = None) -> Path:
        """
        Save the model to disk.

        Args:
            path: Path to save the model. If None, saves to default model directory
                  with auto-generated filename.

        Returns:
            Path where the model was saved

        Raises:
            IOError: If unable to write to the specified path
        """
        # Use default model directory if no path specified
        if path is None:
            self.DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            path = self.DEFAULT_MODEL_DIR / "task_priority_model.pkl"

        # Ensure path is a Path object
        path = Path(path)

        # Create parent directory if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save model and metadata
        model_data = {
            "classifier": self.classifier,
            "regressor": self.regressor,
            "label_encoder": self.label_encoder,
            "feature_names": self.feature_names,
            "is_trained": self.is_trained,
        }

        joblib.dump(model_data, path)

        return path

    @classmethod
    def load(cls, path: Path | None = None) -> TaskPriorityModel:
        """
        Load a trained model from disk.

        Args:
            path: Path to the saved model. If None, loads from default model directory.

        Returns:
            Loaded TaskPriorityModel instance

        Raises:
            FileNotFoundError: If the model file does not exist
        """
        # Use default model path if no path specified
        if path is None:
            path = cls.DEFAULT_MODEL_DIR / "task_priority_model.pkl"

        # Ensure path is a Path object
        path = Path(path)

        model_data = joblib.load(path)

        # Create new instance
        instance = cls()

        # Load attributes
        instance.classifier = model_data["classifier"]
        instance.regressor = model_data["regressor"]
        instance.label_encoder = model_data["label_encoder"]
        instance.feature_names = model_data["feature_names"]
        instance.is_trained = model_data["is_trained"]

        return instance

    def get_feature_importance_explanation(
        self,
        features: dict[str, Any],
    ) -> str:
        """
        Get a detailed explanation of feature importances for prediction.

        Args:
            features: Feature dictionary

        Returns:
            Human-readable explanation of feature importances
        """
        if not self.is_trained:
            return "Model not trained"

        importances = self._extract_feature_importances()

        # Sort features by importance
        sorted_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)

        # Build explanation
        lines = ["Feature Importances:"]

        for feature_name, importance in sorted_features[:10]:
            if importance < 0.01:
                continue

            value = features.get(feature_name, "N/A")
            lines.append(f"  - {feature_name}: {importance:.3f} (value: {value})")

        return "\n".join(lines)
