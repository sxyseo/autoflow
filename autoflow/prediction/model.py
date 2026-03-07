"""
Autoflow Quality Prediction Model

ML model for predicting code quality issues before they manifest.
Uses sklearn's RandomForest classifier for binary prediction (success vs issues).

Usage:
    from autoflow.prediction.model import QualityModel

    model = QualityModel()
    model.train(feature_dicts, outcome_labels)
    prediction = model.predict(feature_dict)
"""

from __future__ import annotations

import joblib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from autoflow.prediction.data_collector import QualityOutcome


@dataclass
class PredictionResult:
    """
    Result of a quality prediction.

    Attributes:
        prediction: Predicted quality outcome (success/needs_changes/failed)
        confidence: Confidence score from 0.0 to 1.0
        feature_importances: Dictionary mapping feature names to importance scores
        rationale: Human-readable explanation of the prediction
    """

    prediction: QualityOutcome
    confidence: float
    feature_importances: dict[str, float] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        # Handle both QualityOutcome enum and string values
        prediction_value = (
            self.prediction.value
            if isinstance(self.prediction, QualityOutcome)
            else self.prediction
        )
        return {
            "prediction": prediction_value,
            "confidence": self.confidence,
            "feature_importances": self.feature_importances,
            "rationale": self.rationale,
        }


class QualityModel:
    """
    ML model for predicting code quality issues.

    Uses sklearn's RandomForest classifier to predict whether a spec
    will succeed or encounter issues based on historical features.

    The model performs binary classification:
        - SUCCESS: Spec will complete successfully
        - ISSUES: Spec will need changes or fail

    Attributes:
        model: The underlying sklearn RandomForestClassifier
        label_encoder: Encoder for converting labels to numeric values
        feature_names: List of feature names used for training
        is_trained: Whether the model has been trained
    """

    # Default model directory for automatic model management
    DEFAULT_MODEL_DIR = Path(".autoflow/models")

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: Optional[int] = None,
        random_state: int = 42,
    ) -> None:
        """
        Initialize the quality model.

        Args:
            n_estimators: Number of trees in the forest
            max_depth: Maximum depth of trees (None for unlimited)
            random_state: Random seed for reproducibility
        """
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            class_weight="balanced",
        )
        self.label_encoder = LabelEncoder()
        self.feature_names: list[str] = []
        self.is_trained = False

    def train(
        self,
        features: list[dict[str, Any]],
        labels: list[str],
    ) -> None:
        """
        Train the model on feature-label pairs.

        Args:
            features: List of feature dictionaries
            labels: List of outcome labels (success/needs_changes/failed)

        Raises:
            ValueError: If features and labels have different lengths
        """
        if len(features) != len(labels):
            raise ValueError(
                f"Features and labels must have same length: "
                f"{len(features)} != {len(labels)}"
            )

        if not features:
            raise ValueError("Cannot train on empty dataset")

        # Convert labels to binary: SUCCESS vs ISSUES
        binary_labels = self._convert_to_binary(labels)

        # Extract feature names from first sample
        self.feature_names = list(features[0].keys())

        # Build feature matrix handling missing features
        feature_matrix = self._build_feature_matrix(features)

        # Train the model
        self.model.fit(feature_matrix, binary_labels)

        # Fit label encoder for later predictions
        self.label_encoder.fit(binary_labels)

        self.is_trained = True

    def predict(self, features: dict[str, Any]) -> PredictionResult:
        """
        Make a prediction for a single feature set.

        Args:
            features: Feature dictionary

        Returns:
            PredictionResult with prediction, confidence, and rationale

        Raises:
            ValueError: If model is not trained
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        # Build feature vector for this sample
        feature_vector = self._build_feature_vector(features)

        # Reshape for sklearn (needs 2D array)
        feature_vector_reshaped = feature_vector.reshape(1, -1)

        # Get prediction and probability
        prediction_binary = self.model.predict(feature_vector_reshaped)[0]
        probabilities = self.model.predict_proba(feature_vector_reshaped)[0]

        # Convert binary prediction back to QualityOutcome
        prediction = self._binary_to_outcome(prediction_binary)

        # Calculate confidence (probability of predicted class)
        confidence = float(probabilities[self.label_encoder.transform([prediction_binary])[0]])

        # Extract feature importances
        feature_importances = self._extract_feature_importances()

        # Generate rationale
        rationale = self._generate_rationale(features, feature_importances, prediction)

        return PredictionResult(
            prediction=prediction,
            confidence=confidence,
            feature_importances=feature_importances,
            rationale=rationale,
        )

    def _convert_to_binary(self, labels: list[str]) -> list[str]:
        """
        Convert multi-class labels to binary (SUCCESS vs ISSUES).

        Args:
            labels: List of outcome labels

        Returns:
            List of binary labels
        """
        binary_labels = []
        for label in labels:
            # Normalize label to lowercase
            label_lower = label.lower()

            # SUCCESS stays as success
            if "success" in label_lower:
                binary_labels.append("success")
            # Everything else is issues (needs_changes or failed)
            else:
                binary_labels.append("issues")

        return binary_labels

    def _binary_to_outcome(self, binary_label: str) -> QualityOutcome:
        """
        Convert binary prediction back to QualityOutcome.

        Args:
            binary_label: Binary label (success or issues)

        Returns:
            QualityOutcome enum value
        """
        if binary_label == "success":
            return QualityOutcome.SUCCESS
        else:
            # For issues, default to needs_changes as it's more actionable
            return QualityOutcome.NEEDS_CHANGES

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

        self.feature_names = sorted(list(all_features))

        # Build matrix row by row
        matrix = []
        for feature_dict in features:
            row = [
                feature_dict.get(name, 0.0)
                for name in self.feature_names
            ]
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
        vector = [
            features.get(name, 0.0)
            for name in self.feature_names
        ]
        return np.array(vector)

    def _extract_feature_importances(self) -> dict[str, float]:
        """
        Extract feature importances from the trained model.

        Returns:
            Dictionary mapping feature names to importance scores
        """
        if not self.is_trained:
            return {}

        importances = self.model.feature_importances_

        return {
            name: float(importance)
            for name, importance in zip(self.feature_names, importances)
        }

    def _generate_rationale(
        self,
        features: dict[str, Any],
        importances: dict[str, float],
        prediction: QualityOutcome,
    ) -> str:
        """
        Generate human-readable rationale for the prediction.

        Args:
            features: Feature dictionary
            importances: Feature importance scores
            prediction: Predicted outcome

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
        # Handle different feature types
        if "num_phases" in feature_name:
            return f"{value} phases"

        elif "num_subtasks" in feature_name:
            return f"{value} subtasks"

        elif "complexity" in feature_name and isinstance(value, (int, float)):
            if value > 70:
                return "high complexity"
            elif value > 40:
                return "moderate complexity"
            else:
                return "low complexity"

        elif "has_test_phase" in feature_name:
            return "includes testing" if value else "no testing phase"

        elif "test_file_ratio" in feature_name and isinstance(value, (int, float)):
            if value < 0.2:
                return "low test coverage"
            elif value > 0.5:
                return "high test coverage"
            else:
                return "moderate test coverage"

        elif "previous_failures" in feature_name and isinstance(value, int):
            if value > 0:
                return f"{value} previous failures"

        elif "file_count" in feature_name and isinstance(value, int):
            return f"{value} files modified"

        elif "parallel_safe" in feature_name:
            return "parallel workflow" if value else "sequential workflow"

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
            path = self.DEFAULT_MODEL_DIR / "quality_model.pkl"

        # Ensure path is a Path object
        path = Path(path)

        # Create parent directory if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save model and metadata
        model_data = {
            "model": self.model,
            "label_encoder": self.label_encoder,
            "feature_names": self.feature_names,
            "is_trained": self.is_trained,
        }

        joblib.dump(model_data, path)

        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "QualityModel":
        """
        Load a trained model from disk.

        Args:
            path: Path to the saved model. If None, loads from default model directory.

        Returns:
            Loaded QualityModel instance

        Raises:
            FileNotFoundError: If the model file does not exist
        """
        # Use default model path if no path specified
        if path is None:
            path = cls.DEFAULT_MODEL_DIR / "quality_model.pkl"

        # Ensure path is a Path object
        path = Path(path)

        model_data = joblib.load(path)

        # Create new instance
        instance = cls()

        # Load attributes
        instance.model = model_data["model"]
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
        sorted_features = sorted(
            importances.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Build explanation
        lines = ["Feature Importances:"]

        for feature_name, importance in sorted_features[:10]:
            if importance < 0.01:
                continue

            value = features.get(feature_name, "N/A")
            lines.append(f"  - {feature_name}: {importance:.3f} (value: {value})")

        return "\n".join(lines)
