"""
Autoflow Data Collector

Collects historical training data by aggregating features with outcomes
from past runs. This data is used to train ML models for quality prediction.

Usage:
    from autoflow.prediction import DataCollector

    collector = DataCollector()
    training_data = collector.collect_training_data()
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from autoflow.prediction.feature_extractor import (
    AgentFeatures,
    FeatureExtractor,
    FeatureVector,
    FileFeatures,
    SpecFeatures,
    TemporalFeatures,
)


class QualityOutcome(str, Enum):
    """
    Quality outcome labels for training data.

    These represent the actual outcome of a spec implementation:
        SUCCESS: Spec completed successfully with no issues
        NEEDS_CHANGES: Spec completed but required fixes/changes
        FAILED: Spec failed to complete or was blocked
    """

    SUCCESS = "success"
    NEEDS_CHANGES = "needs_changes"
    FAILED = "failed"


@dataclass
class TrainingSample:
    """
    A single training sample with features and outcome.

    Attributes:
        spec_id: Unique identifier for the spec
        features: FeatureVector with all extracted features
        outcome: Actual quality outcome
        run_id: Optional run identifier for traceability
    """

    spec_id: str
    features: FeatureVector
    outcome: QualityOutcome
    run_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "spec_id": self.spec_id,
            "features": self.features.to_dict(),
            "outcome": self.outcome.value,
            "run_id": self.run_id,
        }


class DataCollector:
    """
    Collects historical training data from past runs.

    This class aggregates features with outcomes by:
    1. Iterating through .autoflow/runs/ to find completed runs
    2. Extracting features from specs using FeatureExtractor
    3. Mapping run status to quality outcomes
    4. Returning training data as feature-label pairs
    """

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        """
        Initialize the data collector.

        Args:
            root_dir: Root directory of the project. Defaults to current directory.
        """
        self.root_dir = root_dir or Path.cwd()
        self.extractor = FeatureExtractor(root_dir=self.root_dir)

    def collect_training_data(
        self,
        runs_dir: Optional[Path] = None,
        specs_dir: Optional[Path] = None,
    ) -> list[TrainingSample]:
        """
        Collect training data from historical runs.

        Iterates through completed runs, extracts features for each spec,
        and pairs them with the actual outcome.

        Args:
            runs_dir: Path to directory containing run JSON files.
                     Defaults to .autoflow/runs/
            specs_dir: Path to directory containing spec directories.
                     Defaults to .auto-claude/specs/

        Returns:
            List of TrainingSample objects with features and outcomes

        Raises:
            FileNotFoundError: If runs_dir or specs_dir doesn't exist
        """
        if runs_dir is None:
            runs_dir = self.root_dir / ".autoflow" / "runs"
        if specs_dir is None:
            specs_dir = self.root_dir / ".auto-claude" / "specs"

        if not runs_dir.exists():
            raise FileNotFoundError(f"Runs directory not found: {runs_dir}")
        if not specs_dir.exists():
            raise FileNotFoundError(f"Specs directory not found: {specs_dir}")

        # Find all run.json files
        run_files = list(runs_dir.glob("*/run.json"))

        if not run_files:
            return []

        # Group runs by spec
        spec_runs: dict[str, list[dict[str, Any]]] = {}
        for run_file in run_files:
            try:
                run_data = json.loads(run_file.read_text(encoding="utf-8"))
                spec_id = run_data.get("spec", "")
                if spec_id:
                    if spec_id not in spec_runs:
                        spec_runs[spec_id] = []
                    spec_runs[spec_id].append(run_data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        # Collect training samples
        training_samples: list[TrainingSample] = []

        for spec_id, runs in spec_runs.items():
            # Determine the final outcome from all runs for this spec
            outcome = self._determine_outcome(runs)
            if not outcome:
                continue

            # Get a representative run_id for traceability
            run_id = runs[0].get("id", "") if runs else None

            # Extract features for this spec
            spec_path = specs_dir / spec_id
            if not spec_path.exists():
                continue

            try:
                features = self._extract_all_features(spec_path)
                if features:
                    sample = TrainingSample(
                        spec_id=spec_id,
                        features=features,
                        outcome=outcome,
                        run_id=run_id,
                    )
                    training_samples.append(sample)
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                # Skip specs with missing or malformed data
                continue

        return training_samples

    def _determine_outcome(self, runs: list[dict[str, Any]]) -> Optional[QualityOutcome]:
        """
        Determine the final quality outcome from a list of runs.

        Args:
            runs: List of run dictionaries

        Returns:
            QualityOutcome enum value, or None if outcome cannot be determined
        """
        if not runs:
            return None

        # Check the most recent run (last in list)
        # In practice, runs should be sorted by date, but we'll use the last one
        latest_run = runs[-1]
        status = latest_run.get("status", "").lower()

        # Map run status to quality outcome
        if "success" in status or "complete" in status or "done" in status:
            return QualityOutcome.SUCCESS
        elif "needs_changes" in status or "changes" in status:
            return QualityOutcome.NEEDS_CHANGES
        elif "fail" in status or "block" in status or "error" in status:
            return QualityOutcome.FAILED
        elif status == "created":
            # Runs that were just created haven't completed yet
            # Skip them in training data
            return None
        else:
            # Unknown status - default to needs_changes for safety
            return QualityOutcome.NEEDS_CHANGES

    def _extract_all_features(self, spec_path: Path) -> Optional[FeatureVector]:
        """
        Extract all feature types for a spec.

        Args:
            spec_path: Path to the spec directory

        Returns:
            FeatureVector with all extracted features, or None if extraction fails
        """
        try:
            # Extract spec features
            spec_features = self.extractor.extract_spec_features(spec_path)
        except (FileNotFoundError, ValueError):
            spec_features = None

        try:
            # Extract file features
            file_features = self.extractor.extract_file_features()
        except FileNotFoundError:
            file_features = None

        try:
            # Extract agent features
            agent_features = self.extractor.extract_agent_features()
        except FileNotFoundError:
            agent_features = None

        try:
            # Extract temporal features
            temporal_features = self.extractor.extract_temporal_features()
        except Exception:
            temporal_features = None

        # Only return FeatureVector if we have at least spec features
        if spec_features is None:
            return None

        return FeatureVector(
            spec=spec_features,
            file=file_features,
            agent=agent_features,
            temporal=temporal_features,
        )

    def collect_training_data_for_model(
        self,
        runs_dir: Optional[Path] = None,
        specs_dir: Optional[Path] = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Collect training data formatted for ML model training.

        Returns feature vectors and labels as separate lists suitable
        for sklearn's fit() method.

        Args:
            runs_dir: Path to directory containing run JSON files
            specs_dir: Path to directory containing spec directories

        Returns:
            Tuple of (feature_dicts, outcome_labels) where:
                - feature_dicts: List of dictionaries with flattened features
                - outcome_labels: List of outcome strings
        """
        samples = self.collect_training_data(runs_dir, specs_dir)

        feature_dicts = [sample.features.to_dict() for sample in samples]
        outcome_labels = [sample.outcome.value for sample in samples]

        return feature_dicts, outcome_labels
