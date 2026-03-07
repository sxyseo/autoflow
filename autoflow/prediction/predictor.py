"""
Autoflow Quality Predictor

Service class that loads trained models and runs predictions on specs.
Integrates feature extraction with ML model inference for quality prediction.

Usage:
    from autoflow.prediction import QualityPredictor

    predictor = QualityPredictor()
    prediction = predictor.predict_spec(spec_path)
    print(f"Predicted quality: {prediction.prediction}")
    print(f"Confidence: {prediction.confidence}")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from autoflow.prediction.feature_extractor import FeatureExtractor, FeatureVector
from autoflow.prediction.model import PredictionResult, QualityModel


class QualityPredictor:
    """
    Service for predicting code quality from spec characteristics.

    This class loads a trained ML model and provides a simple interface
    for predicting quality outcomes for new specs. It handles:
    - Loading trained models from disk
    - Extracting features from specs
    - Running predictions with confidence scores
    - Providing explainable predictions with rationale

    Attributes:
        model: The trained QualityModel instance
        extractor: FeatureExtractor for extracting features from specs
        model_path: Path to the loaded model file
    """

    # Default model directory
    DEFAULT_MODEL_DIR = Path(".autoflow/models")

    def __init__(
        self,
        model_path: Optional[Path] = None,
        root_dir: Optional[Path] = None,
        allow_untrained: bool = False,
    ) -> None:
        """
        Initialize the quality predictor.

        Args:
            model_path: Path to the trained model file. If None, loads from
                       DEFAULT_MODEL_DIR/quality_model.pkl
            root_dir: Root directory of the project. Defaults to current directory.
            allow_untrained: If True, creates an untrained model if one doesn't exist.
                           If False, raises FileNotFoundError when model is missing.

        Raises:
            FileNotFoundError: If the model file doesn't exist and allow_untrained is False
        """
        # Determine model path
        if model_path is None:
            model_path = self.DEFAULT_MODEL_DIR / "quality_model.pkl"

        self.model_path = Path(model_path)
        self.root_dir = root_dir or Path.cwd()

        # Load or create the model
        try:
            self.model = QualityModel.load(self.model_path)
        except FileNotFoundError:
            if allow_untrained:
                # Create an untrained model for testing/development
                self.model = QualityModel()
            else:
                raise FileNotFoundError(
                    f"Trained model not found at {self.model_path}. "
                    f"Please train a model first using scripts/train_model.py"
                )

        # Initialize feature extractor
        self.extractor = FeatureExtractor(root_dir=self.root_dir)

    def predict(self, features: dict) -> PredictionResult:
        """
        Predict quality outcome from pre-extracted features.

        This is a convenience method for when you have already extracted
        features and just want to run the prediction.

        Args:
            features: Feature dictionary (as returned by FeatureVector.to_dict())

        Returns:
            PredictionResult with prediction, confidence, and rationale

        Raises:
            RuntimeError: If model is not trained
        """
        # Run prediction
        try:
            prediction_result = self.model.predict(features)
        except ValueError as e:
            if "not trained" in str(e).lower():
                raise RuntimeError(
                    "Model is not trained. Please train the model first."
                ) from e
            raise

        return prediction_result

    def predict_spec(self, spec_path: Path) -> PredictionResult:
        """
        Predict quality outcome for a spec.

        Extracts features from the spec and runs the trained model to predict
        the quality outcome with confidence score and rationale.

        Args:
            spec_path: Path to the spec directory containing implementation_plan.json

        Returns:
            PredictionResult with prediction, confidence, and rationale

        Raises:
            FileNotFoundError: If spec_path or implementation_plan.json doesn't exist
            ValueError: If implementation_plan.json is malformed
            RuntimeError: If model is not trained
        """
        # Extract all features for the spec
        feature_vector = self._extract_features(spec_path)

        # Convert to dictionary format for model
        features = feature_vector.to_dict()

        # Run prediction
        return self.predict(features)

    def _extract_features(self, spec_path: Path) -> FeatureVector:
        """
        Extract all feature types for a spec.

        Args:
            spec_path: Path to the spec directory

        Returns:
            FeatureVector with all extracted features

        Raises:
            FileNotFoundError: If spec_path or implementation_plan.json doesn't exist
            ValueError: If implementation_plan.json is malformed
        """
        # Extract spec features (required)
        try:
            spec_features = self.extractor.extract_spec_features(spec_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Spec implementation plan not found: {spec_path / 'implementation_plan.json'}"
            ) from e
        except ValueError as e:
            raise ValueError(f"Invalid implementation plan: {e}") from e

        # Extract file features (optional - may not exist for new specs)
        try:
            file_features = self.extractor.extract_file_features()
        except FileNotFoundError:
            file_features = None

        # Extract agent features (optional - may not exist for new specs)
        try:
            agent_features = self.extractor.extract_agent_features()
        except FileNotFoundError:
            agent_features = None

        # Extract temporal features (always available)
        try:
            temporal_features = self.extractor.extract_temporal_features()
        except Exception:
            temporal_features = None

        return FeatureVector(
            spec=spec_features,
            file=file_features,
            agent=agent_features,
            temporal=temporal_features,
        )

    def is_high_risk(self, prediction: PredictionResult) -> bool:
        """
        Determine if a prediction indicates high risk.

        High risk is defined as:
        - Confidence < 0.6 (low confidence in prediction)
        - Prediction is 'needs_changes' or 'failed'

        Args:
            prediction: PredictionResult to evaluate

        Returns:
            True if prediction indicates high risk, False otherwise
        """
        # Check confidence threshold
        if prediction.confidence < 0.6:
            return True

        # Check prediction outcome
        from autoflow.prediction.data_collector import QualityOutcome

        if prediction.prediction in (
            QualityOutcome.NEEDS_CHANGES,
            QualityOutcome.FAILED,
        ):
            return True

        return False

    def get_prediction_summary(self, prediction: PredictionResult) -> str:
        """
        Get a human-readable summary of the prediction.

        Args:
            prediction: PredictionResult to summarize

        Returns:
            Human-readable summary string
        """
        from autoflow.prediction.data_collector import QualityOutcome

        # Determine risk level
        if self.is_high_risk(prediction):
            risk_level = "HIGH RISK"
        elif prediction.confidence < 0.8:
            risk_level = "MEDIUM RISK"
        else:
            risk_level = "LOW RISK"

        # Build summary
        lines = [
            f"Quality Prediction: {prediction.prediction.value}",
            f"Confidence: {prediction.confidence:.2%}",
            f"Risk Level: {risk_level}",
        ]

        if prediction.rationale:
            lines.append(f"Rationale: {prediction.rationale}")

        if prediction.feature_importances:
            lines.append("\nFeature Importances:")
            for feature, importance in sorted(
                prediction.feature_importances.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]:
                lines.append(f"  - {feature}: {importance:.3f}")

        return "\n".join(lines)

    def create_review_task(
        self,
        spec_path: Path,
        prediction: PredictionResult,
    ) -> bool:
        """
        Create a proactive review task for high-risk predictions.

        When a prediction indicates high risk (low confidence or predicted issues),
        this method adds a new subtask to the implementation plan for manual review.

        Args:
            spec_path: Path to the spec directory containing implementation_plan.json
            prediction: PredictionResult indicating potential quality issues

        Returns:
            True if review task was created, False if prediction was not high-risk

        Raises:
            FileNotFoundError: If implementation_plan.json doesn't exist
            ValueError: If implementation_plan.json is malformed
        """
        # Only create review tasks for high-risk predictions
        if not self.is_high_risk(prediction):
            return False

        plan_file = spec_path / "implementation_plan.json"

        if not plan_file.exists():
            raise FileNotFoundError(f"Implementation plan not found: {plan_file}")

        # Read existing plan
        try:
            plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in implementation plan: {e}") from e

        # Generate subtask ID
        existing_subtasks = []
        for phase in plan_data.get("phases", []):
            for subtask in phase.get("subtasks", []):
                existing_subtasks.append(subtask.get("id", ""))

        # Find next available subtask ID
        subtask_num = 1
        while f"subtask-review-{subtask_num}" in existing_subtasks:
            subtask_num += 1

        new_subtask_id = f"subtask-review-{subtask_num}"

        # Build review task description based on prediction
        from autoflow.prediction.data_collector import QualityOutcome

        risk_reasons = []
        if prediction.confidence < 0.6:
            risk_reasons.append(f"low confidence ({prediction.confidence:.1%})")
        if prediction.prediction == QualityOutcome.NEEDS_CHANGES:
            risk_reasons.append("predicted to need changes")
        elif prediction.prediction == QualityOutcome.FAILED:
            risk_reasons.append("predicted to fail")

        description = (
            f"Quality Review: High-risk prediction ({', '.join(risk_reasons)}). "
            f"Manual review recommended before implementation."
        )

        # Create new review subtask
        review_subtask: dict[str, Any] = {
            "id": new_subtask_id,
            "description": description,
            "service": "autoflow",
            "files_to_modify": [],
            "files_to_create": [],
            "patterns_from": [],
            "verification": {
                "type": "manual",
                "instructions": f"Review prediction rationale: {prediction.rationale}",
            },
            "status": "pending",
            "notes": (
                f"Created by quality prediction system at {datetime.now(UTC).isoformat()}. "
                f"Prediction: {prediction.prediction.value}, "
                f"Confidence: {prediction.confidence:.2%}. "
                f"Rationale: {prediction.rationale}"
            ),
        }

        # Find or create a review phase
        phases = plan_data.get("phases", [])
        review_phase = None
        review_phase_index = len(phases)  # Default to end

        for i, phase in enumerate(phases):
            if "review" in phase.get("name", "").lower():
                review_phase = phase
                review_phase_index = i
                break

        # Add review subtask to the phase
        if review_phase is None:
            # Create a new review phase at the end
            review_phase = {
                "id": "phase-quality-review",
                "name": "Quality Review",
                "type": "review",
                "description": "Manual review tasks for high-risk predictions",
                "depends_on": [],
                "parallel_safe": True,
                "subtasks": [review_subtask],
            }
            phases.append(review_phase)
        else:
            # Add to existing review phase
            if "subtasks" not in review_phase:
                review_phase["subtasks"] = []
            review_phase["subtasks"].append(review_subtask)

        # Update phases in plan data
        plan_data["phases"] = phases

        # Write updated plan back to file
        plan_file.write_text(json.dumps(plan_data, indent=2) + "\n", encoding="utf-8")

        return True
