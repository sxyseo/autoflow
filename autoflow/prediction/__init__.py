"""
Autoflow Prediction - ML-based Quality Prediction

This module provides machine learning-based prediction of code quality issues
before they manifest. Uses patterns from past runs to predict likely problem
areas and suggest proactive fixes.

Features:
- FeatureExtractor: Extract features from specs, files, agents, and temporal data
- QualityModel: ML model for quality prediction
- QualityPredictor: Service for running predictions
- FeedbackCollector: Collect feedback and improve model over time

Usage:
    from autoflow.prediction import FeatureExtractor, QualityPredictor

    extractor = FeatureExtractor()
    features = extractor.extract_spec_features(spec_path)

    predictor = QualityPredictor()
    prediction = predictor.predict_spec(spec_path)
    print(f"Predicted quality: {prediction.prediction}")
    print(f"Confidence: {prediction.confidence}")
"""

from autoflow.prediction.feature_extractor import (
    AgentFeatures,
    FeatureExtractor,
    FeatureVector,
    FileFeatures,
    SpecFeatures,
    TemporalFeatures,
)
from autoflow.prediction.feedback import (
    FeedbackCollector,
    FeedbackSummary,
    PredictionRecord,
    PredictionStatus,
)
from autoflow.prediction.predictor import QualityPredictor

__all__ = [
    # Feature extraction
    "FeatureExtractor",
    "SpecFeatures",
    "FileFeatures",
    "AgentFeatures",
    "TemporalFeatures",
    "FeatureVector",
    # Prediction
    "QualityPredictor",
    # Feedback
    "FeedbackCollector",
    "FeedbackSummary",
    "PredictionRecord",
    "PredictionStatus",
]
